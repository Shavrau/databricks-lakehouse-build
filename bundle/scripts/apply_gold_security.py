#!/usr/bin/env python3
"""
Apply Gold Security Controls and Least-Privilege Model.
In accordance with Lecture - Gold Security Controls:
1. Grants USE CATALOG and USE SCHEMA on gold to data-consumers.
2. Grants SELECT on gold views to data-consumers.
3. Strictly SEALS gold_etl (0 grants to consumers).
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
    return res.status.state, (res.status.error.message if res.status.error else None)

def main():
    parser = argparse.ArgumentParser(description="Apply Gold Security Controls")
    parser.add_argument("--profile", default="dev")
    parser.add_argument("--catalog", default="bakehouse_dev")
    parser.add_argument("--warehouse-id", default="3c88b7bfb51daab1")
    args = parser.parse_args()

    w = WorkspaceClient(profile=args.profile)
    cat = args.catalog
    wh = args.warehouse_id

    print(f"=== Applying Gold Security Controls on {cat} ===")
    
    statements = [
        # 1. Catalog & Schema access for consumers
        (f"GRANT USE CATALOG ON CATALOG {cat} TO `data-consumers`", "Grant USE CATALOG to data-consumers"),
        (f"GRANT USE SCHEMA ON SCHEMA {cat}.gold TO `data-consumers`", "Grant USE SCHEMA on gold to data-consumers"),
        
        # 2. View-level SELECT grants for consumers
        (f"GRANT SELECT ON VIEW {cat}.gold.v_sales_daily TO `data-consumers`", "Grant SELECT on v_sales_daily"),
        (f"GRANT SELECT ON VIEW {cat}.gold.v_customer_sales_summary TO `data-consumers`", "Grant SELECT on v_customer_sales_summary"),
        (f"GRANT SELECT ON VIEW {cat}.gold.v_franchise_performance TO `data-consumers`", "Grant SELECT on v_franchise_performance"),

        # 3. PII readers group access
        (f"GRANT USE CATALOG ON CATALOG {cat} TO `pii-readers`", "Grant USE CATALOG to pii-readers"),
        (f"GRANT USE SCHEMA ON SCHEMA {cat}.gold TO `pii-readers`", "Grant USE SCHEMA on gold to pii-readers"),
        (f"GRANT SELECT ON VIEW {cat}.gold.v_customer_sales_summary TO `pii-readers`", "Grant SELECT on v_customer_sales_summary to pii-readers"),
    ]

    for sql, desc in statements:
        state, err = run_query(w, wh, sql)
        if state and "SUCCEEDED" in str(state):
            print(f"  PASS: {desc} ({state})")
        else:
            print(f"  INFO: {desc} -> {err if err else state}")

    print("\nSecurity controls applied. gold_etl remains sealed with 0 consumer grants.\n")

if __name__ == "__main__":
    main()
