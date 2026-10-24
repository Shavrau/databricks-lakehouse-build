"""
Final Acceptance Testing Suite – Definition of Done (D1 to D6)
Validates the entire Bakehouse Lakehouse platform across Databricks Serverless compute,
Unity Catalog schemas, Master Lakeflow Job, data integrity, and documentation deliverables.
"""

import os
import sys
from pathlib import Path
from databricks.sdk import WorkspaceClient

def main():
    print("=" * 80)
    print("BAKEHOUSE MEDALLION LAKEHOUSE – FINAL ACCEPTANCE TEST SUITE (PHASE 6)")
    print("=" * 80)

    w = WorkspaceClient(profile="dev")
    catalog = "bakehouse_dev"
    warehouse_id = "3c88b7bfb51daab1"
    all_passed = True
    test_results = []

    def log_result(test_id, name, passed, details=""):
        nonlocal all_passed
        if not passed:
            all_passed = False
        status = "PASS" if passed else "FAIL"
        test_results.append((test_id, name, status, details))
        print(f"[{status}] {test_id}: {name}")
        if details:
            print(f"       Details: {details}")

    def execute_query(sql):
        resp = w.statement_execution.execute_statement(
            warehouse_id=warehouse_id,
            catalog=catalog,
            statement=sql,
            wait_timeout="50s"
        )
        if resp.status and resp.status.state and resp.status.state.value == "FAILED":
            err = resp.status.error.message if resp.status.error else "Unknown SQL error"
            raise RuntimeError(f"Query failed: {err}\nSQL: {sql}")
        if resp.result and resp.result.data_array:
            return resp.result.data_array
        return []

    # -------------------------------------------------------------------------
    # CRITERION D1: Functional Pipeline & Master Orchestration Job
    # -------------------------------------------------------------------------
    print("\n--- Validating Criterion D1: Functional Pipeline & Master Orchestration ---")
    try:
        # Check Master Job
        all_jobs = list(w.jobs.list())
        jobs = [j for j in all_jobs if "Bakehouse Master Lakehouse Orchestrator" in (j.settings.name or "")]

        if jobs:
            # Must call w.jobs.get() to expand tasks
            job = w.jobs.get(jobs[0].job_id)
            tasks = job.settings.tasks or []
            task_keys = [t.task_key for t in tasks]
            expected_tasks = [
                "refresh_medallion_pipeline",
                "run_gold_views_ddl",
                "run_quality_checks",
                "run_silver_maintenance",
                "run_bronze_maintenance"
            ]
            has_all_tasks = all(t in task_keys for t in expected_tasks)
            log_result("D1-T1", "Master Lakeflow Job & DAG Topology", has_all_tasks,
                       f"Job ID: {job.job_id}, Found {len(tasks)} tasks: {task_keys}")
        else:
            log_result("D1-T1", "Master Lakeflow Job & DAG Topology", False, "Master job not found in workspace")

        # Check Pipeline state
        pipelines = list(w.pipelines.list_pipelines(filter="name LIKE '%Bakehouse%'"))
        if pipelines:
            p = pipelines[0]
            pipe_info = w.pipelines.get(p.pipeline_id)
            state = pipe_info.state.value if pipe_info.state else "UNKNOWN"
            log_result("D1-T2", "Medallion Declarative Pipeline Status", state in ["IDLE", "RUNNING"],
                       f"Pipeline ID: {p.pipeline_id}, State: {state}")
        else:
            log_result("D1-T2", "Medallion Declarative Pipeline Status", False, "Pipeline not found")

    except Exception as e:
        log_result("D1-ERR", "D1 Execution Check", False, str(e))

    # -------------------------------------------------------------------------
    # CRITERION D2: Data Validation Check Suites (Counts, Keys, Sums, SCD2)
    # -------------------------------------------------------------------------
    print("\n--- Validating Criterion D2: Data Integrity & Quality Checks ---")
    try:
        # Bronze counts
        b_tx = int(execute_query("SELECT COUNT(*) FROM bakehouse_dev.bronze.transactions")[0][0])
        b_cu = int(execute_query("SELECT COUNT(*) FROM bakehouse_dev.bronze.customers")[0][0])
        b_fr = int(execute_query("SELECT COUNT(*) FROM bakehouse_dev.bronze.franchises")[0][0])
        b_su = int(execute_query("SELECT COUNT(*) FROM bakehouse_dev.bronze.suppliers")[0][0])
        b_tz = int(execute_query("SELECT COUNT(*) FROM bakehouse_dev.bronze.franchise_time_zones")[0][0])

        log_result("D2-T1", "Bronze Ingestion Completeness",
                   b_tx == 3333 and b_fr >= 48 and b_su >= 27 and b_tz == 48,
                   f"tx={b_tx}, cu={b_cu}, fr={b_fr}, su={b_su}, tz={b_tz}")

        # Silver reconciliation & SCD2
        s_tx = int(execute_query("SELECT COUNT(*) FROM bakehouse_dev.silver.transactions")[0][0])
        s_rev = float(execute_query("SELECT ROUND(SUM(total_price), 2) FROM bakehouse_dev.silver.transactions")[0][0])
        s_scd2_curr = int(execute_query("SELECT COUNT(*) FROM bakehouse_dev.silver.customers WHERE is_current = true")[0][0])
        s_scd2_hist = int(execute_query("SELECT COUNT(*) FROM bakehouse_dev.silver.customers_scd2")[0][0])

        log_result("D2-T2", "Silver Reconciliation & SCD2 Historization",
                   s_tx == 3333 and s_rev == 66471.0 and s_scd2_curr == 303 and s_scd2_hist == 309,
                   f"tx={s_tx}, rev=${s_rev:.2f}, curr_cust={s_scd2_curr}, total_hist_versions={s_scd2_hist}")

        # Gold ETL & Financial Reconciliation
        g_tx = int(execute_query("SELECT SUM(transaction_count) FROM bakehouse_dev.gold_etl.sales_daily")[0][0])
        g_rev = float(execute_query("SELECT ROUND(SUM(gross_sales), 2) FROM bakehouse_dev.gold_etl.sales_daily")[0][0])

        log_result("D2-T3", "Gold Financial & Transaction Reconciliation",
                   g_tx == 3333 and g_rev == 66471.0,
                   f"gold_tx={g_tx}, gold_rev=${g_rev:.2f} (Matches Silver $66,471.00)")

        # Quality Check Results Audit Table
        qc_rows = execute_query("""
            SELECT rule_family, rule_name, status, observed_value 
            FROM bakehouse_dev.gold_etl.quality_results 
            ORDER BY run_timestamp DESC 
            LIMIT 4
        """)
        all_qc_pass = all(r[2] == "PASS" for r in qc_rows) and len(qc_rows) == 4
        qc_details = "; ".join([f"{r[0]}/{r[1]}: {r[2]}" for r in qc_rows])
        log_result("D2-T4", "Business Quality Rules Audit (4 Families)", all_qc_pass, qc_details)

    except Exception as e:
        log_result("D2-ERR", "D2 Execution Check", False, str(e))

    # -------------------------------------------------------------------------
    # CRITERION D3: Unity Catalog Schemas, Tags & Governance
    # -------------------------------------------------------------------------
    print("\n--- Validating Criterion D3: Unity Catalog Governance & Security ---")
    try:
        schemas = [r[0] for r in execute_query(f"SHOW SCHEMAS IN {catalog}")]
        expected_schemas = ["landing", "bronze", "silver", "gold_etl", "gold"]
        has_schemas = all(s in schemas for s in expected_schemas)

        log_result("D3-T1", "Unity Catalog Schema Structure", has_schemas,
                   f"Found: {schemas}")

        # Gold Views in consumer schema
        views = [r[0] for r in execute_query("""
            SELECT table_name 
            FROM system.information_schema.views 
            WHERE table_catalog = 'bakehouse_dev' AND table_schema = 'gold'
        """)]
        expected_views = ["v_sales_daily", "v_customer_sales_summary", "v_franchise_performance"]
        has_views = all(v in views for v in expected_views)
        log_result("D3-T2", "Consumer Interface Views in 'gold'", has_views, f"Views: {views}")

        # Dynamic Masking check (as non-member)
        cust_view_sample = execute_query("""
            SELECT first_name, last_name, email_address, lifetime_spend 
            FROM bakehouse_dev.gold.v_customer_sales_summary 
            LIMIT 1
        """)[0]
        first_n, last_n, email_val, spend = cust_view_sample
        is_masked = ("***" in first_n and "***" in last_n and "***" in email_val)
        log_result("D3-T3", "Dynamic Privacy Masking on Customer View", is_masked,
                   f"first_name='{first_n}', email='{email_val}', spend=${spend}")

    except Exception as e:
        log_result("D3-ERR", "D3 Execution Check", False, str(e))

    # -------------------------------------------------------------------------
    # CRITERION D4: Documentation Delivered
    # -------------------------------------------------------------------------
    print("\n--- Validating Criterion D4: Documentation Deliverables ---")
    base_dir = Path("d:/PI/lakehouse_build")
    required_docs = [
        ("D4-DOC1", base_dir / "01_discovery_scoping" / "scoping_document.md"),
        ("D4-DOC2", base_dir / "02_foundation_kickoff" / "foundation_readiness_record.md"),
        ("D4-DOC3", base_dir / "03_bronze" / "01_bronze_design.md"),
        ("D4-DOC4", base_dir / "04_silver" / "01_silver_design.md"),
        ("D4-DOC5", base_dir / "05_gold" / "01_gold_design.md"),
        ("D4-DOC6", base_dir / "06_optimization_governance_close" / "01_scaling_and_delta_optimization.md"),
        ("D4-DOC7", base_dir / "06_optimization_governance_close" / "02_governance_at_scale.md"),
        ("D4-DOC8", base_dir / "06_optimization_governance_close" / "03_serving_bi_orchestration.md"),
        ("D4-DOC9", base_dir / "06_optimization_governance_close" / "operations_runbook.md"),
        ("D4-DOC10", base_dir / "06_optimization_governance_close" / "user_guides" / "01_analysts_guide.md"),
        ("D4-DOC11", base_dir / "06_optimization_governance_close" / "user_guides" / "02_bi_developers_guide.md"),
        ("D4-DOC12", base_dir / "06_optimization_governance_close" / "user_guides" / "03_data_engineers_guide.md"),
        ("D4-DOC13", base_dir / "06_optimization_governance_close" / "user_guides" / "04_platform_operators_guide.md"),
        ("D4-DOC14", base_dir / "06_optimization_governance_close" / "cost_optimization_summary.md"),
        ("D4-DOC15", base_dir / "06_optimization_governance_close" / "stakeholder_signoff.md"),
    ]

    all_docs_exist = True
    for test_id, path in required_docs:
        exists = path.exists() and path.stat().st_size > 100
        if not exists:
            all_docs_exist = False
        log_result(test_id, f"Document: {path.name}", exists, f"Path: {path}")

    log_result("D4-ALL", "Comprehensive Documentation Suite Complete", all_docs_exist)

    # -------------------------------------------------------------------------
    # CRITERION D5: Scope Budget Maintained
    # -------------------------------------------------------------------------
    print("\n--- Validating Criterion D5: Scope Budget ---")
    try:
        # Table counts per layer
        bronze_tbls = len(execute_query(f"SHOW TABLES IN {catalog}.bronze"))
        silver_tbls = len(execute_query(f"SHOW TABLES IN {catalog}.silver"))
        gold_etl_tbls = len(execute_query(f"SHOW TABLES IN {catalog}.gold_etl"))
        gold_views_cnt = len(execute_query(f"SHOW VIEWS IN {catalog}.gold"))

        budget_ok = (
            bronze_tbls <= 10 and
            silver_tbls <= 10 and
            gold_etl_tbls <= 10 and
            gold_views_cnt <= 10
        )
        log_result("D5-T1", "Layer Table Budgets (<= 10 tables per layer)", budget_ok,
                   f"Bronze: {bronze_tbls}/10, Silver: {silver_tbls}/10, Gold ETL: {gold_etl_tbls}/10, Gold Views: {gold_views_cnt}/10")

        # Pipelines budget: exactly 1
        pipe_cnt = len(pipelines)
        log_result("D5-T2", "Medallion Pipeline Budget (Exactly 1 pipeline)", pipe_cnt == 1,
                   f"Found {pipe_cnt} medallion pipeline(s)")

    except Exception as e:
        log_result("D5-ERR", "D5 Execution Check", False, str(e))

    # -------------------------------------------------------------------------
    # CRITERION D6: Governance Controls (PCI Card Numbers Removed)
    # -------------------------------------------------------------------------
    print("\n--- Validating Criterion D6: Security & Governance Compliance ---")
    try:
        # Verify full PAN card number dropped after Bronze, only payment_card_last_four preserved
        silver_cols = [r[0].lower() for r in execute_query("DESCRIBE bakehouse_dev.silver.transactions")]
        has_full_pan = any(c in ["card_number", "credit_card_number", "pan", "card_num"] for c in silver_cols)
        has_last_four = "payment_card_last_four" in silver_cols
        pci_silver_ok = (not has_full_pan) and has_last_four

        log_result("D6-T1", "PCI Compliance: Full Card Numbers Excluded, Only Last Four Preserved in Silver", pci_silver_ok,
                   f"Columns: payment_card_last_four present: {has_last_four}, Full card number present: {has_full_pan}")

        gold_cols = [r[0].lower() for r in execute_query("DESCRIBE bakehouse_dev.gold.v_sales_daily")]
        has_card_gold = any("card" in c for c in gold_cols)
        log_result("D6-T2", "PCI Compliance: Credit Card Numbers Excluded from Gold", not has_card_gold,
                   f"Gold view columns: {gold_cols}")

    except Exception as e:
        log_result("D6-ERR", "D6 Execution Check", False, str(e))

    # -------------------------------------------------------------------------
    # SUMMARY
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    passed_cnt = sum(1 for _, _, s, _ in test_results if s == "PASS")
    total_cnt = len(test_results)
    print(f"FINAL ACCEPTANCE SUMMARY: {passed_cnt}/{total_cnt} TESTS PASSED")
    print("=" * 80)

    if all_passed:
        print("\nALL DEFINITION OF DONE CRITERIA (D1 TO D6) ARE EMPIRICALLY MET!")
        return 0
    else:
        print("\nONE OR MORE ACCEPTANCE TESTS FAILED. INVESTIGATE OUTPUT ABOVE.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
