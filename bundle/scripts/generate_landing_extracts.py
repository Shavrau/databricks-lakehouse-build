#!/usr/bin/env python3
"""
Generate Landing Extracts from samples.bakehouse into Unity Catalog Volumes.
Supports:
  - batch1: Historical snapshot (80% boundary) for transactions and baseline dimensions.
  - batch2: Incremental replay for transactions (remaining 20%).
  - dim_batch2: Evolution batch for dimensions (5 updated customers, 3 new customers, 1 missing supplier).
  - dim_batch3: Second evolution batch (1 re-updated customer, 1 reactivated supplier, 1 updated franchise).
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
    print("Exporting Suppliers Snapshot (27 rows)...")
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

def stage_dim_batch2(w: WorkspaceClient, catalog: str, warehouse_id: str):
    print("=== Staging Dimension Batch 2 (SCD Type 2 Evolution & Soft Delete) ===")
    base_vol = f"/Volumes/{catalog}/landing/extracts"

    # 1. Customers: 5 updated, 3 inserted -> 303 total rows
    print("Staging Customers Batch 2 (5 updates, 3 inserts, batch_ts = 2024-05-15 00:00:00)...")
    cust_query = """
        SELECT customerID, first_name, last_name, email_address, phone_number, address, city, state, country, continent, postal_zip_code, gender
        FROM samples.bakehouse.sales_customers
        ORDER BY customerID
    """
    cols, data = execute_query(w, warehouse_id, cust_query)
    updated_data = []
    for r in data:
        cid = int(r[0])
        row_copy = list(r)
        if cid == 2000000:
            row_copy[3] = "updated.cust0@bakehouse-vip.com"
            row_copy[5] = "100 New Baker Street"
        elif cid == 2000001:
            row_copy[3] = "updated.cust1@bakehouse-vip.com"
            row_copy[5] = "200 New Baker Street"
        elif cid == 2000002:
            row_copy[3] = "updated.cust2@bakehouse-vip.com"
            row_copy[5] = "300 New Baker Street"
        elif cid == 2000003:
            row_copy[3] = "updated.cust3@bakehouse-vip.com"
            row_copy[5] = "400 New Baker Street"
        elif cid == 2000004:
            row_copy[3] = "updated.cust4@bakehouse-vip.com"
            row_copy[5] = "500 New Baker Street"
        updated_data.append(row_copy)
    
    # Add 3 new synthetic customers
    updated_data.append(["2009001", "Alice", "Morgan", "alice.morgan@bakehouse.test", "555-0191", "10 Alpha Way", "Austin", "TX", "USA", "North America", "78701", "Female"])
    updated_data.append(["2009002", "Bob", "Chen", "bob.chen@bakehouse.test", "555-0192", "20 Beta Ave", "Denver", "CO", "USA", "North America", "80202", "Male"])
    updated_data.append(["2009003", "Carlos", "Silva", "carlos.silva@bakehouse.test", "555-0193", "30 Gamma Blvd", "Miami", "FL", "USA", "North America", "33101", "Male"])

    csv_bytes = to_csv_bytes(cols, updated_data)
    path = f"{base_vol}/customers/customers_2024051500.csv"
    w.files.upload(path, io.BytesIO(csv_bytes), overwrite=True)
    print(f"Uploaded {len(updated_data)} rows to {path}")

    # 2. Suppliers: 1 missing supplier (supplierID = 4000010 removed) -> 26 rows
    print("Staging Suppliers Batch 2 (supplierID = 4000010 removed, batch_ts = 2024-05-15 00:00:00)...")
    supp_query = """
        SELECT supplierID, name, ingredient, continent, city, district, size, longitude, latitude, approved
        FROM samples.bakehouse.sales_suppliers
        WHERE supplierID != 4000010
        ORDER BY supplierID
    """
    cols, data = execute_query(w, warehouse_id, supp_query)
    csv_bytes = to_csv_bytes(cols, data)
    path = f"{base_vol}/suppliers/suppliers_2024051500.csv"
    w.files.upload(path, io.BytesIO(csv_bytes), overwrite=True)
    print(f"Uploaded {len(data)} rows to {path}")
    print("Dimension Batch 2 staging completed.\n")

def stage_dim_batch3(w: WorkspaceClient, catalog: str, warehouse_id: str):
    print("=== Staging Dimension Batch 3 (Reactivations & Multi-version) ===")
    base_vol = f"/Volumes/{catalog}/landing/extracts"

    # 1. Customers: customer 2000000 updated again -> 303 total rows
    print("Staging Customers Batch 3 (customerID = 2000000 updated again, batch_ts = 2024-05-16 00:00:00)...")
    cust_query = """
        SELECT customerID, first_name, last_name, email_address, phone_number, address, city, state, country, continent, postal_zip_code, gender
        FROM samples.bakehouse.sales_customers
        ORDER BY customerID
    """
    cols, data = execute_query(w, warehouse_id, cust_query)
    updated_data = []
    for r in data:
        cid = int(r[0])
        row_copy = list(r)
        if cid == 2000000:
            row_copy[3] = "cust0.latest@bakehouse-executive.com"
            row_copy[5] = "999 Executive Way"
        elif cid in (2000001, 2000002, 2000003, 2000004):
            idx = cid - 2000000
            row_copy[3] = f"updated.cust{idx}@bakehouse-vip.com"
            row_copy[5] = f"{idx+1}00 New Baker Street"
        updated_data.append(row_copy)
    
    updated_data.append(["2009001", "Alice", "Morgan", "alice.morgan@bakehouse.test", "555-0191", "10 Alpha Way", "Austin", "TX", "USA", "North America", "78701", "Female"])
    updated_data.append(["2009002", "Bob", "Chen", "bob.chen@bakehouse.test", "555-0192", "20 Beta Ave", "Denver", "CO", "USA", "North America", "80202", "Male"])
    updated_data.append(["2009003", "Carlos", "Silva", "carlos.silva@bakehouse.test", "555-0193", "30 Gamma Blvd", "Miami", "FL", "USA", "North America", "33101", "Male"])

    csv_bytes = to_csv_bytes(cols, updated_data)
    path = f"{base_vol}/customers/customers_2024051600.csv"
    w.files.upload(path, io.BytesIO(csv_bytes), overwrite=True)
    print(f"Uploaded {len(updated_data)} rows to {path}")

    # 2. Suppliers: supplier 4000010 restored -> 27 rows
    print("Staging Suppliers Batch 3 (supplierID = 4000010 restored, batch_ts = 2024-05-16 00:00:00)...")
    supp_query = """
        SELECT supplierID, name, ingredient, continent, city, district, size, longitude, latitude, approved
        FROM samples.bakehouse.sales_suppliers
        ORDER BY supplierID
    """
    cols, data = execute_query(w, warehouse_id, supp_query)
    csv_bytes = to_csv_bytes(cols, data)
    path = f"{base_vol}/suppliers/suppliers_2024051600.csv"
    w.files.upload(path, io.BytesIO(csv_bytes), overwrite=True)
    print(f"Uploaded {len(data)} rows to {path}")

    # 3. Franchises: franchiseID = 3000002 attribute update (size = 'Mega') -> 48 rows
    print("Staging Franchises Batch 3 (franchiseID = 3000002 size='Mega', batch_ts = 2024-05-16 00:00:00)...")
    fran_query = """
        SELECT franchiseID, name, city, district, zipcode, country, size, longitude, latitude, supplierID
        FROM samples.bakehouse.sales_franchises
        ORDER BY franchiseID
    """
    cols, data = execute_query(w, warehouse_id, fran_query)
    fran_updated = []
    for r in data:
        row_copy = list(r)
        if int(row_copy[0]) == 3000002:
            row_copy[6] = "Mega"
        fran_updated.append(row_copy)
    
    csv_bytes = to_csv_bytes(cols, fran_updated)
    path = f"{base_vol}/franchises/franchises_2024051600.csv"
    w.files.upload(path, io.BytesIO(csv_bytes), overwrite=True)
    print(f"Uploaded {len(fran_updated)} rows to {path}")
    print("Dimension Batch 3 staging completed.\n")

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
    parser.add_argument("--stage", choices=["batch1", "batch2", "dim_batch2", "dim_batch3", "all", "clean"], required=True)
    args = parser.parse_args()

    w = WorkspaceClient(profile=args.profile)

    if args.stage == "clean":
        clean_extracts(w, args.catalog)
    elif args.stage == "batch1":
        stage_batch1(w, args.catalog, args.warehouse_id)
    elif args.stage == "batch2":
        stage_batch2(w, args.catalog, args.warehouse_id)
    elif args.stage == "dim_batch2":
        stage_dim_batch2(w, args.catalog, args.warehouse_id)
    elif args.stage == "dim_batch3":
        stage_dim_batch3(w, args.catalog, args.warehouse_id)
    elif args.stage == "all":
        stage_batch1(w, args.catalog, args.warehouse_id)
        stage_batch2(w, args.catalog, args.warehouse_id)

if __name__ == "__main__":
    main()
