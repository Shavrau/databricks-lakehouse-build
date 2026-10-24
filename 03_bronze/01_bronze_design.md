# 01 · Bronze Layer Design and Ingestion Architecture

| | |
|---|---|
| **Phase** | 3 – Land & Solidify Bronze |
| **Status** | APPROVED – Under Implementation |
| **Platform** | Databricks Serverless, Lakeflow Spark Declarative Pipelines |
| **Traces to** | [scoping_document.md](../01_discovery_scoping/scoping_document.md), [foundation_readiness_record.md](../02_foundation_kickoff/foundation_readiness_record.md) |

---

## 1. The Bronze Contract

The Bronze layer serves as the **fidelity copy** of all source extract files landing in the Unity Catalog Volume (`/Volumes/${catalog}/landing/extracts/`). It fulfills three fundamental promises:

1. **Fidelity:** Preserves raw source columns and values exactly as landed. No business logic, no column renaming (retaining source PascalCase/camelCase), and no premature type casting.
2. **Completeness:** Captures 100% of delivered records across all batches with exactly-once ingestion semantics via Auto Loader (`STREAM read_files`).
3. **Replayability:** Every downstream layer (Silver, Gold) can be completely dropped and reconstructed solely from the Bronze tables and their lineage metadata.

---

## 2. Ingestion Topology

All five Bronze tables are defined as **Streaming Tables** in `${catalog}.bronze` powered by Lakeflow Spark Declarative Pipelines:

| Bronze Table | Upstream Volume Extract Path | Delivery Pattern | Source System Tag |
|---|---|---|---|
| `transactions` | `/Volumes/${catalog}/landing/extracts/transactions` | Snapshot (80th pct) + Incremental replay | `POS` |
| `customers` | `/Volumes/${catalog}/landing/extracts/customers` | Full snapshot reload + append | `CRM` |
| `franchises` | `/Volumes/${catalog}/landing/extracts/franchises` | Full snapshot reload + append | `FRANCHISE_REGISTRY` |
| `suppliers` | `/Volumes/${catalog}/landing/extracts/suppliers` | Full snapshot reload + append | `SUPPLIER_REGISTRY` |
| `franchise_time_zones` | `/Volumes/${catalog}/landing/extracts/time_zones` | Reference seed reload + append | `REFERENCE_SEED` |

---

## 3. Standard Ingestion Lineage Metadata

Every Bronze record is augmented with 5 standardized audit columns:

| Column | Data Type | Extraction Logic | Role |
|---|---|---|---|
| `_ingested_at` | `TIMESTAMP` | `current_timestamp()` | Wall-clock arrival timestamp for freshness SLA calculation and pipeline execution auditing |
| `_source_file` | `STRING` | `_metadata.file_path` | Absolute Volume path of the exact input file that produced this record |
| `_source_system` | `STRING` | Literal tag (`'POS'`, `'CRM'`, etc.) | Upstream source platform identifier |
| `_schema_version` | `STRING` | Literal `'v1.0'` | Tracks the schema revision of the source extract file |
| `_batch_ts` | `TIMESTAMP` | Extracted from file name (`<source>_yyyyMMddHH.csv`) | Deterministic logical batch timestamp; anchors downstream Type 2 SCD versions and soft deletes |

---

## 4. Replay Simulation Strategy (Snapshot + Incremental)

From our Step 0 profiling of `samples.bakehouse.sales_transactions`, we observed:
- Total rows: 3,333
- Min `dateTime`: `2024-05-01 00:03:28 UTC`
- Max `dateTime`: `2024-05-17 11:48:38 UTC`

To demonstrate production-grade incremental processing:
1. **Batch 1 (Historical Snapshot - 80th Percentile):**
   - Transações de `2024-05-01 00:00:00` a `2024-05-14 04:00:00 UTC` (~2,666 linhas) em `transactions_2024050100.csv`.
   - Snapshots completos de `customers` (300 linhas), `franchises` (48 linhas), `suppliers` (48 linhas) e `franchise_time_zones` (48 linhas) com `_batch_ts = 2024-05-01T00:00:00Z`.
2. **Batch 2 (Incremental Replay - Remaining 20%):**
   - Transações de `2024-05-14 04:00:00` a `2024-05-17 12:00:00 UTC` (~667 linhas) em `transactions_2024051404.csv`.
   - Staged sequentially into the landing volume to demonstrate Auto Loader discovering new files without reprocessing Batch 1.

---

## 5. Physical Table Maintenance

- **Predictive Optimization:** Verified enabled at the metastore level (`ENABLE` on `metastore_aws_us_east_2`). Unity Catalog automatically schedules compaction and vacuuming based on query heuristics.
- **Manual Maintenance Safety Net:** A Lakeflow Job executes `OPTIMIZE` and `ANALYZE TABLE <tbl> COMPUTE STATISTICS FOR ALL COLUMNS` off-hours to refresh optimizer statistics for query planning.
- **Layout Rule:** Bronze tables utilize standard compaction without manual Liquid Clustering or Z-ORDER, preserving raw write performance.

---

## 6. Acceptance Criteria (Gate G3)

| Test ID | Assertion Description | Target |
|---|---|---|
| **B-T1** | Ingestion metadata columns present and non-null | 100% of rows in all 5 Bronze tables |
| **B-T2** | Row count reconciliation | Bronze count == sum of rows delivered in landed CSV files |
| **B-T3** | Key uniqueness integrity | `customerID`, `franchiseID`, `supplierID` 100% unique; `transactionID` reflects exactly the 3 source duplicates |
| **B-T4** | Timestamp bounds | `MIN/MAX(dateTime)` in Bronze matches the boundary of landed batches |
| **B-T5** | Unity Catalog governance tags | Schema and tables tagged with `layer=bronze`, comments populated |
| **B-T6** | Ingestion idempotence | Triggering pipeline when no new files arrive results in 0 additional rows |
