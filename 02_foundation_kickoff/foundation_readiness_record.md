# Foundation Readiness Record – Bakehouse Lakehouse Build

| | |
|---|---|
| **Customer** | Bakehouse (global cookie franchise) |
| **Phase** | 2 – Foundation & Kickoff (exit gate) |
| **Version / status** | v1.0 VERIFIED – **Workspace Foundation Ready** |
| **Platform** | Databricks Free Edition, Serverless on AWS (`us-east-2`) |
| **Verified Date** | 2026-10-24 |

> This document certifies that all platform foundation prerequisites, compute choices, data design rules, and governance guardrails are in place and empirically verified against the live workspace before any Bronze data ingestion begins.

---

## 1. Verified Architecture & Compute Footprint

| Item | Measured / Live Reality | Verification Reference |
|---|---|---|
| **Cloud Provider** | AWS | Workspace host: `dbc-654c8244-a596.cloud.databricks.com` |
| **Cloud Region** | `us-east-2` (Ohio) | Metastore: `metastore_aws_us_east_2` |
| **Metastore ID** | `32856ce5-ce37-4c56-96d1-54b637fa40e8` | Confirmed via Catalog metadata |
| **Predictive Optimization** | `ENABLE` (Inherited from metastore) | Automated maintenance enabled for managed tables |
| **SQL Warehouse** | `Serverless Starter Warehouse` (ID `3c88b7bfb51daab1`) | Size: `2X-Small`, Serverless, Verified RUNNING |
| **Managed Storage Root** | `s3://dbstorage-prod-3q3ts/uc/254e92e7-b7a1-4fab-89c0-1b143a173564/32856ce5-ce37-4c56-96d1-54b637fa40e8` | Databricks Default Storage |

---

## 2. Verified Data Inventory & Key Assertions (`samples.bakehouse`)

Every source table was queried and verified via Unity Catalog metadata and statistics:

| Entity / Table | Source Rows | Unique Key | Distinct Key Count | Key Unique? | Verified Time Range |
|---|---|---|---|---|---|
| `sales_customers` | 300 | `customerID` | 300 | **YES** (0 NULLs) | N/A (Dimension snapshot) |
| `sales_franchises` | 48 | `franchiseID` | 48 | **YES** (0 NULLs) | N/A (No time zone column in source) |
| `sales_suppliers` | 48 | `supplierID` | 48 | **YES** (0 NULLs) | N/A (Dimension snapshot) |
| `sales_transactions` | 3,333 | `transactionID` | 3,330 | **NO (3 Duplicates)** | `2024-05-01 00:03:28` to `2024-05-17 11:48:38 UTC` |

### Critical Findings from Verification
1. **Duplicate Transactions in Source:** `sales_transactions` contains 3,333 rows but only 3,330 distinct `transactionID`s. Deduplication in Silver on `transaction_id` is an active business requirement, not an artificial scenario.
2. **Time Boundary for History:** Earliest transaction is `2024-05-01 00:03:28 UTC`. Dimension Batch 1 must be stamped with `_batch_ts = 2024-05-01T00:00:00Z` so all transactions find an active customer version (Test K-T8 satisfied).
3. **Missing Franchise Time Zones:** Confirmed that `sales_franchises` has no time zone attribute. The `franchise_time_zones` reference seed (48 rows, CL-1) is mandatory.

---

## 3. Deployed Governance & Storage Guardrails

### 3.1 Catalogs & Schemas (Live)
- **Development:** `bakehouse_dev` (`landing`, `bronze`, `silver`, `gold`)
- **Production:** `bakehouse_prod` (`landing`, `bronze`, `silver`, `gold`)

### 3.2 Governed Landing Volumes (Live)
- `bakehouse_dev.landing.extracts` (Managed UC Volume)
- `bakehouse_prod.landing.extracts` (Managed UC Volume)
- Landing path convention: `/Volumes/bakehouse_<env>/landing/extracts/<source>/<yyyy>/<mm>/<dd>/<source>_<yyyymmddHH>.csv`

### 3.3 Identity & Ownership Model
- Workspace SCIM Groups created:
  - `platform-admins` (ID `2127135363159834`)
  - `data-engineers` (ID `2125654010944575`)
  - `data-consumers` (ID `2120829434948563`)
  - `pii-readers` (ID `2125472640450325`)
  - `ingestion-writers` (ID `2121120628885901`)
- **Documented Deviation:** Unity Catalog `ALTER ... OWNER TO` in this Free Edition workspace requires account-level SCIM federation. As planned in [03_governance_guardrails.md](03_governance_guardrails.md) §3, `rhian.souza@programmers.com.br` acts as interim owner while the target group matrix remains documented.

---

## 4. Code Structure & Automation (DABs)

- Bundle configuration established at [`bundle/databricks.yml`](../bundle/databricks.yml).
- Validated via `databricks bundle validate` for both `dev` and `prod` targets.
- Target mapping:
  - `dev`: Catalog `bakehouse_dev`, development mode.
  - `prod`: Catalog `bakehouse_prod`, production mode.

---

## 5. Foundation Acceptance Gate (G0 Passed)

| Test ID | Description | Status | Evidence |
|---|---|---|---|
| **F-T1** | Region Alignment (Workspace, Metastore, Storage in same region) | **PASS** | AWS `us-east-2` confirmed |
| **F-T2** | Core services availability (Serverless, UC Volumes, SQL Warehouse) | **PASS** | Starter Warehouse running, Volumes created |
| **F-T3** | Serverless compute configuration | **PASS** | Configured in bundle & warehouse |
| **K-T1** | Key distinct count profiling on sources | **PASS** | 300 customers, 48 franchises, 48 suppliers, 3330 distinct transactions |
| **S-T1** | Ownership & Interim Owner documentation | **PASS** | Interim owner recorded; 5 groups provisioned |
| **S-T2** | No DBFS for persistent data | **PASS** | Volumes `/Volumes/...` configured |
| **S-T3** | Managed tables in managed storage root | **PASS** | Catalogs bound to Default Storage |
| **S-T7** | `bundle validate` passes for dev and prod | **PASS** | Zero errors reported |

---

## 6. Exit Gate Conclusion

The platform foundation is verified, deployed, and solid. The workspace is officially ready to receive the **Phase 3 (Bronze)** build.
