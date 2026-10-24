#!/usr/bin/env python3
"""
Generate Landing Extracts from samples.bakehouse into Unity Catalog Volumes.
Implements the 'Snapshot then Incremental' pattern for Phase 3 Bronze.
"""
import argparse
import csv
import io
import sys
from databricks.sdk import WorkspaceClient

TIMEZONE_MAP = {
    # Australia
    "Sydney": "Australia/Sydney",
    "Melbourne": "Australia/Melbourne",
    "Brisbane": "Australia/Brisbane",
    "Perth": "Australia/Perth",
    "Adelaide": "Australia/Adelaide",
    "Gold Coast": "Australia/Brisbane",
    # Japan
    "Tokyo": "Asia/Tokyo",
    "Kobe": "Asia/Tokyo",
    "Kyoto": "Asia/Tokyo",
    "Osaka": "Asia/Tokyo",
    "Hiroshima": "Asia/Tokyo",
    "Nagoya": "Asia/Tokyo",
    "Fukuoka": "Asia/Tokyo",
    "Sapporo": "Asia/Tokyo",
    "Sendai": "Asia/Tokyo",
    "Hiratsuka": "Asia/Tokyo",
    "Kanazawa": "Asia/Tokyo",
    "Suita": "Asia/Tokyo",
    "Niigata": "Asia/Tokyo",
    "Chiba": "Asia/Tokyo",
    "Kumamoto": "Asia/Tokyo",
    "Kagoshima": "Asia/Tokyo",
    "Naha": "Asia/Tokyo",
    "Okayama": "Asia/Tokyo",
    "Matsuyama": "Asia/Tokyo",
    "Aomori": "Asia/Tokyo",
    # US & Canada
    "San Francisco": "America/Los_Angeles",
    "Los Angeles": "America/Los_Angeles",
    "Seattle": "America/Los_Angeles",
    "Portland": "America/Los_Angeles",
    "Chicago": "America/Chicago",
    "New Orleans": "America/Chicago",
    "Austin": "America/Chicago",
    "Nashville": "America/Chicago",
    "Denver": "America/Denver",
    "Las Vegas": "America/Los_Angeles",
    "Miami": "America/New_York",
    "Philadelphia": "America/New_York",
    "Boston": "America/New_York",
    "Washington D.C.": "America/New_York",
    "Honolulu": "Pacific/Honolulu",
    "Vancouver": "America/Vancouver",
    # Europe
    "Amsterdam": "Europe/Amsterdam",
    "Paris": "Europe/Paris",
    "Berlin": "Europe/Berlin",
    "Rome": "Europe/Rome",
    "Stockholm": "Europe/Stockholm",
}

def execute_query(w: WorkspaceClient, warehouse_id: str, query: str):
    response = w.statement_execution.execute_statement(
        statement=query,
        warehouse_id=warehouse_id,
        wait_timeout="50s"
    )
    cols = [c.name for c in response.manifest.schema.columns]
    data = response.result.data_array if response.result and response.result.data_array else []
    return cols, data

def to_csv_bytes(cols, data) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(cols)
    for row in data:
        writer.writerow(row)
    return output.getvalue().encode("utf-8")

def stage_batch1(w: WorkspaceClient, catalog: str, warehouse_id: str):
    print("=== Staging Batch 1 (Historical Snapshot - 80% boundary) ===")
    base_vol = f"/Volumes/{catalog}/landing/extracts"

    # 1. Transactions Batch 1 (<= 2024-05-14 07:13:18)
    print("Exporting Transactions Batch 1 (~2,666 rows)...")
    tx_query = """
        SELECT transactionID, customerID, franchiseID, dateTime, product, quantity, unitPrice, totalPrice, paymentMethod, cardNumber
        FROM samples.bakehouse.sales_transactions
        WHERE dateTime <= '2024-05-14 07:13:18'
        ORDER BY dateTime, transactionID
    """
    cols, data = execute_query(w, warehouse_id, tx_query)
    csv_bytes = to_csv_bytes(cols, data)
    path = f"{base_vol}/transactions/transactions_2024050100.csv"
    w.files.upload(path, io.BytesIO(csv_bytes), overwrite=True)
    print(f"Uploaded {len(data)} rows to {path}")

    # 2. Customers Snapshot
    print("Exporting Customers Snapshot (300 rows)...")
    cust_query = """
        SELECT customerID, first_name, last_name, email_address, phone_number, address, city, state, country, continent, postal_zip_code, gender
        FROM samples.bakehouse.sales_customers
        ORDER BY customerID
    """
    cols, data = execute_query(w, warehouse_id, cust_query)
    csv_bytes = to_csv_bytes(cols, data)
    path = f"{base_vol}/customers/customers_2024050100.csv"
    w.files.upload(path, io.BytesIO(csv_bytes), overwrite=True)
    print(f"Uploaded {len(data)} rows to {path}")

    # 3. Franchises Snapshot
    print("Exporting Franchises Snapshot (48 rows)...")
    fran_query = """
        SELECT franchiseID, name, city, district, zipcode, country, size, longitude, latitude, supplierID
        FROM samples.bakehouse.sales_franchises
        ORDER BY franchiseID
    """
    cols, data = execute_query(w, warehouse_id, fran_query)
    csv_bytes = to_csv_bytes(cols, data)
    path = f"{base_vol}/franchises/franchises_2024050100.csv"
    w.files.upload(path, io.BytesIO(csv_bytes), overwrite=True)
    print(f"Uploaded {len(data)} rows to {path}")

    # 4. Suppliers Snapshot
    print("Exporting Suppliers Snapshot (48 rows)...")
    supp_query = """
        SELECT supplierID, name, ingredient, continent, city, district, size, longitude, latitude, approved
        FROM samples.bakehouse.sales_suppliers
        ORDER BY supplierID
    """
    cols, data = execute_query(w, warehouse_id, supp_query)
    csv_bytes = to_csv_bytes(cols, data)
    path = f"{base_vol}/suppliers/suppliers_2024050100.csv"
    w.files.upload(path, io.BytesIO(csv_bytes), overwrite=True)
    print(f"Uploaded {len(data)} rows to {path}")

    # 5. Franchise Time Zones Reference Seed
    print("Generating Franchise Time Zones Reference Seed (48 rows)...")
    tz_rows = []
    for r in data:  # We can pull franchise cities from fran_query result
        pass
    # Re-iterate franchises for timezone mapping:
    _, fran_data = execute_query(w, warehouse_id, "SELECT franchiseID, city FROM samples.bakehouse.sales_franchises ORDER BY franchiseID")
    tz_cols = ["franchise_id", "time_zone"]
    tz_data = []
    for fid, city in fran_data:
        tz = TIMEZONE_MAP.get(city, "UTC")
        tz_data.append([fid, tz])
    
    csv_bytes = to_csv_bytes(tz_cols, tz_data)
    path = f"{base_vol}/time_zones/franchise_time_zones_2024050100.csv"
    w.files.upload(path, io.BytesIO(csv_bytes), overwrite=True)
    print(f"Uploaded {len(tz_data)} rows to {path}")
    print("Batch 1 staging completed successfully.\n")

def stage_batch2(w: WorkspaceClient, catalog: str, warehouse_id: str):
    print("=== Staging Batch 2 (Incremental Replay - Remaining 20%) ===")
    base_vol = f"/Volumes/{catalog}/landing/extracts"

    print("Exporting Transactions Batch 2 (~667 rows)...")
    tx_query = """
        SELECT transactionID, customerID, franchiseID, dateTime, product, quantity, unitPrice, totalPrice, paymentMethod, cardNumber
        FROM samples.bakehouse.sales_transactions
        WHERE dateTime > '2024-05-14 07:13:18'
        ORDER BY dateTime, transactionID
    """
    cols, data = execute_query(w, warehouse_id, tx_query)
    csv_bytes = to_csv_bytes(cols, data)
    path = f"{base_vol}/transactions/transactions_2024051404.csv"
    w.files.upload(path, io.BytesIO(csv_bytes), overwrite=True)
    print(f"Uploaded {len(data)} rows to {path}")
    print("Batch 2 staging completed successfully.\n")

def clean_extracts(w: WorkspaceClient, catalog: str):
    print(f"Cleaning extract files in /Volumes/{catalog}/landing/extracts...")
    base_vol = f"/Volumes/{catalog}/landing/extracts"
    for sub in ["transactions", "customers", "franchises", "suppliers", "time_zones"]:
        try:
            for item in w.files.list_directory_contents(f"{base_vol}/{sub}"):
                w.files.delete(item.path)
                print(f"Deleted: {item.path}")
        except Exception:
            pass
    print("Cleanup done.")

def main():
    parser = argparse.ArgumentParser(description="Stage extracts into landing volume")
    parser.add_argument("--profile", default="dev", help="Databricks CLI profile")
    parser.add_argument("--catalog", default="bakehouse_dev", help="Target catalog")
    parser.add_argument("--warehouse-id", default="3c88b7bfb51daab1", help="SQL Warehouse ID")
    parser.add_argument("--stage", choices=["batch1", "batch2", "all", "clean"], required=True)
    args = parser.parse_args()

    w = WorkspaceClient(profile=args.profile)

    if args.stage == "clean":
        clean_extracts(w, args.catalog)
    elif args.stage == "batch1":
        stage_batch1(w, args.catalog, args.warehouse_id)
    elif args.stage == "batch2":
        stage_batch2(w, args.catalog, args.warehouse_id)
    elif args.stage == "all":
        stage_batch1(w, args.catalog, args.warehouse_id)
        stage_batch2(w, args.catalog, args.warehouse_id)

if __name__ == "__main__":
    main()
