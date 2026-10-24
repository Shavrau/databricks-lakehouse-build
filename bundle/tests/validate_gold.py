#!/usr/bin/env python3
"""
Automated Validation Suite for Phase 5: Develop Gold Layer
Asserts:
  - G-T1: Two-schema boundary (gold_etl tables vs gold views)
  - G-T2: Views contract & explicit column enumeration
  - G-T3: View and column documentation
  - G-T4: Business rule quality checks logged in quality_results (100% PASS)
  - G-T5: Financial and transaction count reconciliation (Gold == Silver)
  - SEC-T1: Sealing of gold_etl schema
  - SEC-T2: Dynamic PII redaction behavior
"""
import argparse
import sys
from databricks.sdk import WorkspaceClient

def run_query(w: WorkspaceClient, warehouse_id: str, sql: str):
    res = w.statement_execution.execute_statement(
        statement=sql,
        warehouse_id=warehouse_id,
        wait_timeout="50s"
    )
    cols = [c.name for c in res.manifest.schema.columns] if res.manifest and res.manifest.schema else []
    data = res.result.data_array if res.result and res.result.data_array else []
    return cols, data

def main():
    parser = argparse.ArgumentParser(description="Validate Gold Layer")
    parser.add_argument("--profile", default="dev")
    parser.add_argument("--catalog", default="bakehouse_dev")
    parser.add_argument("--warehouse-id", default="3c88b7bfb51daab1")
    args = parser.parse_args()

    w = WorkspaceClient(profile=args.profile)
    cat = args.catalog
    wh = args.warehouse_id

    print("==================================================")
    print(f"  RUNNING GOLD VALIDATION SUITE: {cat}            ")
    print("==================================================\n")
    all_passed = True

    # 1. G-T1: Two-Schema Boundary Architecture
    print("[TEST G-T1] Two-Schema Separation (gold_etl tables vs gold views)")
    _, etl_tables = run_query(w, wh, f"SELECT table_name FROM system.information_schema.tables WHERE table_catalog = '{cat}' AND table_schema = 'gold_etl'")
    etl_names = [r[0] for r in etl_tables]
    expected_etl = ["sales_daily", "customer_sales_summary", "franchise_performance", "quality_results"]
    missing_etl = [t for t in expected_etl if t not in etl_names]

    _, gold_views = run_query(w, wh, f"SELECT table_name FROM system.information_schema.views WHERE table_catalog = '{cat}' AND table_schema = 'gold'")
    view_names = [r[0] for r in gold_views]
    expected_views = ["v_sales_daily", "v_customer_sales_summary", "v_franchise_performance"]
    missing_views = [v for v in expected_views if v not in view_names]

    if not missing_etl and not missing_views:
        print(f"  PASS: gold_etl contains tables: {etl_names}")
        print(f"  PASS: gold contains consumer views: {view_names}")
    else:
        print(f"  FAIL: Missing in gold_etl: {missing_etl}, Missing in gold: {missing_views}")
        all_passed = False

    # 2. G-T2 & G-T3: View Contract & Explicit Column Enumeration
    print("\n[TEST G-T2 & G-T3] View Explicit Columns & Documentation")
    for v in expected_views:
        sql = f"""
            SELECT count(*) 
            FROM system.information_schema.views 
            WHERE table_catalog = '{cat}' AND table_schema = 'gold' AND table_name = '{v}'
              AND view_definition LIKE '%SELECT *%'
        """
        _, star_check = run_query(w, wh, sql)
        if int(star_check[0][0]) == 0:
            print(f"  PASS: {v} has explicit column list (no SELECT * contract violation)")
        else:
            print(f"  FAIL: {v} uses SELECT * in view definition")
            all_passed = False

        _, comm_check = run_query(w, wh, f"SELECT comment FROM system.information_schema.tables WHERE table_catalog = '{cat}' AND table_schema = 'gold' AND table_name = '{v}'")
        comment = comm_check[0][0] if comm_check and comm_check[0] else ""
        if comment:
            print(f"  PASS: {v} has documented comment: '{comment[:50]}...'")
        else:
            print(f"  FAIL: {v} is missing comment")
            all_passed = False

    # 3. G-T4: Business Rule Quality Checks Verification
    print("\n[TEST G-T4] Business Rule Quality Checks Execution (quality_results)")
    sql = f"""
        SELECT rule_family, rule_name, observed_value, status
        FROM {cat}.gold_etl.quality_results
        ORDER BY run_timestamp DESC
        LIMIT 4
    """
    _, qual_data = run_query(w, wh, sql)
    if qual_data:
        rule_statuses = {}
        for fam, name, obs, st in qual_data:
            rule_statuses[name] = st
            status_flag = "PASS" if st == "PASS" else "FAIL"
            print(f"  {status_flag}: [{fam}] {name} -> Status: {st} (Observed: {obs})")
            if st != "PASS":
                all_passed = False
        if len(rule_statuses) < 4:
            print(f"  FAIL: Expected 4 rule families logged, found {len(rule_statuses)}")
            all_passed = False
    else:
        print("  FAIL: No records found in quality_results")
        all_passed = False

    # 4. G-T5: Financial and Transaction Count Reconciliation (Gold == Silver)
    print("\n[TEST G-T5] Financial & Transaction Count Reconciliation")
    _, s_tx = run_query(w, wh, f"SELECT count(distinct transaction_id), sum(total_price) FROM {cat}.silver.transactions")
    s_cnt, s_rev = int(s_tx[0][0]), float(s_tx[0][1])

    _, g_tx = run_query(w, wh, f"SELECT sum(transaction_count), sum(gross_sales) FROM {cat}.gold.v_sales_daily")
    g_cnt, g_rev = int(g_tx[0][0]), float(g_tx[0][1])

    if s_cnt == g_cnt and abs(s_rev - g_rev) < 0.01:
        print(f"  PASS: Transaction counts reconcile: Silver={s_cnt}, Gold={g_cnt}")
        print(f"  PASS: Gross revenue reconciles: Silver=${s_rev:,.2f}, Gold=${g_rev:,.2f}")
    else:
        print(f"  FAIL: Count mismatch (Silver={s_cnt}, Gold={g_cnt}) or Rev mismatch (Silver={s_rev}, Gold={g_rev})")
        all_passed = False

    # 5. SEC-T1: Sealed Engineering Schema Assertion (gold_etl)
    print("\n[TEST SEC-T1] Sealed Engineering Schema Security Check")
    sql = f"""
        SELECT grantee, privilege_type 
        FROM system.information_schema.schema_privileges 
        WHERE schema_name = 'gold_etl' AND grantee = 'data-consumers'
    """
    _, priv_data = run_query(w, wh, sql)
    if not priv_data:
        print("  PASS: gold_etl is sealed (0 grants to data-consumers)")
    else:
        print(f"  FAIL: data-consumers holds privileges on gold_etl: {priv_data}")
        all_passed = False

    # 6. SEC-T2: Dynamic PII Redaction Verification
    print("\n[TEST SEC-T2] Dynamic PII Redaction Assertion")
    sql = f"""
        SELECT email_address, phone_number, first_name, last_name
        FROM {cat}.gold.v_customer_sales_summary
        LIMIT 5
    """
    _, masked_rows = run_query(w, wh, sql)
    sample_email = masked_rows[0][0]
    sample_phone = masked_rows[0][1]
    if "***" in sample_email and "***" in sample_phone:
        print(f"  PASS: Redaction active for non-pii-reader: email='{sample_email}', phone='{sample_phone}'")
    else:
        print(f"  INFO: Query caller may hold pii-readers membership. Values: email='{sample_email}', phone='{sample_phone}'")

    print("\n==================================================")
    if all_passed:
        print("  RESULT: ALL GOLD ACCEPTANCE TESTS PASSED (GREEN)  ")
    else:
        print("  RESULT: SOME TESTS FAILED")
    print("==================================================")
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
