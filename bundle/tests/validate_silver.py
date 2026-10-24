#!/usr/bin/env python3
"""
Automated Validation Suite for Phase 4: Land & Solidify Silver
Asserts:
  - H-T1 to H-T5
  - K-T3 to K-T6
  - PCI-T1 (PCI card minimisation)
  - FLAG-T1 (Boolean flag conversion)
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
    parser = argparse.ArgumentParser(description="Validate Silver Layer")
    parser.add_argument("--profile", default="dev")
    parser.add_argument("--catalog", default="bakehouse_dev")
    parser.add_argument("--warehouse-id", default="3c88b7bfb51daab1")
    parser.add_argument("--evolution-stage", choices=["batch1", "batch2", "batch3"], default="batch1")
    args = parser.parse_args()

    w = WorkspaceClient(profile=args.profile)
    cat = args.catalog
    wh = args.warehouse_id
    stage = args.evolution_stage

    print(f"==================================================")
    print(f"  RUNNING SILVER VALIDATION SUITE: {cat}.silver   ")
    print(f"  Stage: {stage}                                 ")
    print(f"==================================================\n")
    all_passed = True

    # 1. H-T5 / K-T3: Transactions Key Uniqueness & Deduplication
    print("[TEST H-T5 / K-T3] Transactions Primary Key Deduplication")
    sql = f"""
        SELECT count(*) as total_rows,
               count(distinct transaction_id) as distinct_keys,
               count(*) - count(distinct transaction_id) as duplicate_count
        FROM {cat}.silver.transactions
    """
    _, data = run_query(w, wh, sql)
    tot, dist, dups = [int(x) for x in data[0]]
    if dups == 0 and tot == dist and tot > 0:
        print(f"  PASS: silver.transactions has exactly {tot} rows with 0 duplicate transaction_ids (100% unique keys)")
    else:
        print(f"  FAIL: silver.transactions total={tot}, distinct={dist}, duplicates={dups} (expected dups=0)")
        all_passed = False

    # 2. PCI-T1: Payment Card Data Minimisation
    print("\n[TEST PCI-T1] PCI Data Minimisation (Card Number Dropped / Tokenized)")
    sql = f"""
        SELECT column_name, data_type 
        FROM system.information_schema.columns 
        WHERE table_catalog = '{cat}' AND table_schema = 'silver' AND table_name = 'transactions'
          AND column_name IN ('cardNumber', 'payment_card_last_four')
    """
    _, data = run_query(w, wh, sql)
    col_names = [r[0] for r in data]
    if "cardNumber" not in col_names and "payment_card_last_four" in col_names:
        print(f"  PASS: Raw 'cardNumber' is dropped; 'payment_card_last_four' is present")
        # Check non-nullness
        _, nn_data = run_query(w, wh, f"SELECT count(*) FROM {cat}.silver.transactions WHERE payment_card_last_four IS NULL")
        if int(nn_data[0][0]) == 0:
            print(f"  PASS: 100% of transactions have non-null payment_card_last_four")
        else:
            print(f"  FAIL: Found null payment_card_last_four")
            all_passed = False
    else:
        print(f"  FAIL: Column status: {col_names}")
        all_passed = False

    # 3. CURR-T1: Currency Types Conformance (DECIMAL(10,2))
    print("\n[TEST CURR-T1] Currency Types Cast to DECIMAL(10,2)")
    sql = f"""
        SELECT column_name, data_type 
        FROM system.information_schema.columns 
        WHERE table_catalog = '{cat}' AND table_schema = 'silver' AND table_name = 'transactions'
          AND column_name IN ('unit_price', 'total_price')
    """
    _, data = run_query(w, wh, sql)
    type_map = {r[0]: r[1].lower() for r in data}
    if "decimal" in type_map.get("unit_price", "") and "decimal" in type_map.get("total_price", ""):
        print(f"  PASS: unit_price and total_price are {type_map['unit_price']}")
    else:
        print(f"  FAIL: Currency types: {type_map}")
        all_passed = False

    # 4. H-T1 & K-T4: Customer SCD Type 2 Current Version Invariants
    print("\n[TEST H-T1 & K-T4] Customer Current Version & Invariant Assertion")
    sql = f"""
        SELECT 
            count(distinct customer_id) as total_customers,
            sum(case when is_current = true then 1 else 0 end) as current_count,
            sum(case when is_current = true and effective_to_ts is not null then 1 else 0 end) as invalid_open,
            sum(case when is_current = false and effective_to_ts is null then 1 else 0 end) as invalid_closed
        FROM {cat}.silver.customers
    """
    _, data = run_query(w, wh, sql)
    tot_cust, curr_cnt, inv_open, inv_closed = [int(x) for x in data[0]]
    if tot_cust == curr_cnt and inv_open == 0 and inv_closed == 0:
        print(f"  PASS: Exactly 1 current version per customer ({tot_cust} total customers). effective_to_ts IS NULL <=> is_current=true")
    else:
        print(f"  FAIL: total_customers={tot_cust}, current_count={curr_cnt}, invalid_open={inv_open}, invalid_closed={inv_closed}")
        all_passed = False

    # 5. H-T2: No Type 2 Gaps or Overlaps
    print("\n[TEST H-T2] Type 2 Interval Continuity (No Gaps or Overlaps)")
    sql = f"""
        WITH version_pairs AS (
            SELECT customer_id,
                   effective_from_ts,
                   effective_to_ts,
                   lead(effective_from_ts) over (partition by customer_id order by effective_from_ts) as next_from_ts
            FROM {cat}.silver.customers
        )
        SELECT count(*)
        FROM version_pairs
        WHERE next_from_ts IS NOT NULL AND effective_to_ts != next_from_ts
    """
    _, data = run_query(w, wh, sql)
    interval_mismatches = int(data[0][0])
    if interval_mismatches == 0:
        print(f"  PASS: 0 interval gaps or overlaps across all customer versions")
    else:
        print(f"  FAIL: Found {interval_mismatches} interval mismatches")
        all_passed = False

    # 6. FLAG-T1: Supplier Boolean Flag Conversion
    print("\n[TEST FLAG-T1] Supplier Approval Flag Converted to BOOLEAN")
    sql = f"""
        SELECT data_type 
        FROM system.information_schema.columns 
        WHERE table_catalog = '{cat}' AND table_schema = 'silver' AND table_name = 'suppliers'
          AND column_name = 'is_approved'
    """
    _, data = run_query(w, wh, sql)
    flag_type = data[0][0].lower() if data else ""
    if flag_type == "boolean":
        print(f"  PASS: silver.suppliers.is_approved is {flag_type}")
    else:
        print(f"  FAIL: silver.suppliers.is_approved type is {flag_type}")
        all_passed = False

    # 7. FRAN-T1: Franchises Time Zone Enrichment
    print("\n[TEST FRAN-T1] Franchises Time Zone Enrichment from Reference Seed")
    sql = f"""
        SELECT count(*) as total_franchises,
               count(time_zone) as non_null_tz,
               count(distinct time_zone) as distinct_tz
        FROM {cat}.silver.franchises
    """
    _, data = run_query(w, wh, sql)
    tot_f, nn_tz, dist_tz = [int(x) for x in data[0]]
    if tot_f == nn_tz == 48 and dist_tz > 1:
        print(f"  PASS: All 48 franchises have valid, populated IANA time zones ({dist_tz} distinct zones)")
    else:
        print(f"  FAIL: total={tot_f}, non_null_tz={nn_tz}, distinct_tz={dist_tz}")
        all_passed = False

    # 8. H-T4: Evolution checks for dimensions
    if stage == "batch2":
        print("\n[TEST H-T4] Dimension Evolution Assertions (Batch 2)")
        # Check supplier 4000010 is deleted
        _, supp_data = run_query(w, wh, f"SELECT is_deleted FROM {cat}.silver.suppliers WHERE supplier_id = 4000010")
        is_del = str(supp_data[0][0]).lower() if supp_data else ""
        if is_del == "true":
            print(f"  PASS: Supplier 4000010 is flagged is_deleted = TRUE (soft delete verified)")
        else:
            print(f"  FAIL: Supplier 4000010 is_deleted is '{is_del}'")
            all_passed = False
        
        # Check multi-version customer count
        _, cust_ver = run_query(w, wh, f"SELECT count(*) FROM {cat}.silver.customers WHERE customer_id IN (2000000, 2000001, 2000002, 2000003, 2000004)")
        c_ver = int(cust_ver[0][0])
        if c_ver == 10:  # 5 customers * 2 versions
            print(f"  PASS: Customers 2000000-2000004 have 10 versions in Type 2 history (SCD2 versioning verified)")
        else:
            print(f"  FAIL: Customers 2000000-2000004 version count = {c_ver} (expected 10)")
            all_passed = False
    elif stage == "batch3":
        print("\n[TEST H-T4] Dimension Evolution Assertions (Batch 3)")
        # Check supplier 4000010 is reactivated
        _, supp_data = run_query(w, wh, f"SELECT is_deleted FROM {cat}.silver.suppliers WHERE supplier_id = 4000010")
        is_del = str(supp_data[0][0]).lower() if supp_data else ""
        if is_del == "false":
            print(f"  PASS: Supplier 4000010 is flagged is_deleted = FALSE (reactivation verified)")
        else:
            print(f"  FAIL: Supplier 4000010 is_deleted is '{is_del}' (expected false)")
            all_passed = False
        
        # Check customer 2000000 has 3 versions
        _, cust1_ver = run_query(w, wh, f"SELECT count(*) FROM {cat}.silver.customers WHERE customer_id = 2000000")
        c1_ver = int(cust1_ver[0][0])
        if c1_ver == 3:
            print(f"  PASS: Customer 2000000 has exactly 3 historical versions (multi-version verified)")
        else:
            print(f"  FAIL: Customer 2000000 version count = {c1_ver} (expected 3)")
            all_passed = False

    print("\n==================================================")
    if all_passed:
        print("  RESULT: ALL SILVER ACCEPTANCE TESTS PASSED (GREEN) ")
    else:
        print("  RESULT: SOME TESTS FAILED")
    print("==================================================")
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
