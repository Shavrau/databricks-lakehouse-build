#!/usr/bin/env python3
"""
Provision gold_etl schema in Unity Catalog (bakehouse_dev and bakehouse_prod).
Implements the two-schema architecture: gold_etl (sealed engineering) vs gold (consumer views).
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
    return res.status.state

def main():
    parser = argparse.ArgumentParser(description="Provision Gold Schemas")
    parser.add_argument("--profile", default="dev")
    parser.add_argument("--warehouse-id", default="3c88b7bfb51daab1")
    args = parser.parse_args()

    w = WorkspaceClient(profile=args.profile)
    wh = args.warehouse_id

    catalogs = ["bakehouse_dev", "bakehouse_prod"]

    print("=== Provisioning gold_etl Schemas ===")
    for cat in catalogs:
        print(f"Creating {cat}.gold_etl...")
        create_sql = f"""
            CREATE SCHEMA IF NOT EXISTS {cat}.gold_etl
            COMMENT 'Sealed engineering schema for Gold materialized tables, working tables, and quality check logs'
        """
        state = run_query(w, wh, create_sql)
        print(f"  {cat}.gold_etl created: {state}")

        tag_sql = f"ALTER SCHEMA {cat}.gold_etl SET TAGS ('layer' = 'gold_etl', 'access' = 'engineering_only')"
        state_tag = run_query(w, wh, tag_sql)
        print(f"  Tags set on {cat}.gold_etl: {state_tag}")

        tag_gold = f"ALTER SCHEMA {cat}.gold SET TAGS ('layer' = 'gold', 'access' = 'consumer_facing')"
        state_gold = run_query(w, wh, tag_gold)
        print(f"  Tags set on {cat}.gold: {state_gold}")

    print("Gold schemas provisioned successfully.\n")

if __name__ == "__main__":
    main()
