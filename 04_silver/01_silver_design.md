# 01 · Silver Layer Design and Conformance Architecture

| | |
|---|---|
| **Phase** | 4 – Land & Solidify Silver |
| **Status** | APPROVED – Under Implementation |
| **Platform** | Databricks Serverless, Lakeflow Spark Declarative Pipelines |
| **Traces to** | [scoping_document.md](../01_discovery_scoping/scoping_document.md), [04_ingestion_historization_decisions.md](../01_discovery_scoping/04_ingestion_historization_decisions.md), [02_data_design_keys_time.md](../02_foundation_kickoff/02_data_design_keys_time.md) |

---

## 1. The Silver Transformation Contract

The Silver layer is where raw data from Bronze is cleansed, conformed, and historized into reliable enterprise datasets. In accordance with the *Transformation and Business Mappings* lecture:

1. **Bounded Scope:** Silver handles column renaming to `snake_case`, data type casting (especially currency to `DECIMAL(10,2)`), grouping normalization, deduplication, and historization.
2. **Exclusion of Heavy Logic:** Multi-table business aggregations and KPI calculations are strictly deferred to the Gold authoring layer.
3. **Escalation Rulings:**
   - **`total_price` vs `quantity * unit_price`:** Silent recomputation is prohibited. The landed `totalPrice` from Bronze is cast to `DECIMAL(10,2)` as authoritative, and an expectation constraint audits arithmetic consistency.
   - **Data Minimisation (PCI/GDPR):** The raw payment card number (`cardNumber`) landed in Bronze is dropped at the Silver boundary. Only `payment_card_last_four` is retained for transaction lookups and audit tracing.

---

## 2. Table Schemas and Column Mappings

### 2.1 `silver.transactions` (Fact Table)
- **Source:** `bakehouse_dev.bronze.transactions`
- **Delivery:** Streaming Table with SCD Type 1 deduplication on `transaction_id` (via `dp.create_auto_cdc_flow`). Eliminates the 3 duplicate keys present in the source extract.
- **Physical Layout:** Liquid Clustering on `(transaction_date_utc, franchise_id)`.

| Bronze Column | Silver Column | Target Data Type | Transformation Logic | Rationale |
|---|---|---|---|---|
| `transactionID` | `transaction_id` | `INT` | Explicit cast | Natural primary key, `snake_case` |
| `customerID` | `customer_id` | `INT` | Explicit cast | Foreign key to `silver.customers` |
| `franchiseID` | `franchise_id` | `INT` | Explicit cast | Foreign key to `silver.franchises` |
| `dateTime` | `transaction_ts` | `TIMESTAMP` | Explicit cast (UTC) | Event time semantic convention |
| *(derived)* | `transaction_date_utc` | `DATE` | `to_date(dateTime)` | Daily partitioning & Liquid Clustering key |
| `product` | `product` | `STRING` | Passthrough | Dimension attribute |
| `quantity` | `quantity` | `INT` | Explicit cast | Sold units |
| `unitPrice` | `unit_price` | `DECIMAL(10,2)` | Cast to decimal | Currency must never stay integer or float |
| `totalPrice` | `total_price` | `DECIMAL(10,2)` | Cast to decimal | Authoritative billed total; never recomputed |
| `paymentMethod` | `payment_method` | `STRING` | `lower(trim(paymentMethod))` | Normalization for grouping |
| `cardNumber` | `payment_card_last_four` | `STRING` | `substring(string(cardNumber), -4, 4)` | PCI compliance; raw number dropped |
| *(lineage)* | `_source_file`, `_source_system`, `_schema_version`, `_ingested_at`, `_batch_ts` | Standard types | Passthrough | End-to-end lineage tracking |

---

### 2.2 `silver.customers` (Dimension Table with SCD Type 2)
- **Source:** `bakehouse_dev.bronze.customers`
- **Delivery:** Maintained by Lakeflow Declarative Auto CDC (`stored_as_scd_type=2`) sequenced by `_batch_ts`. Exposes both native temporal columns and conformed Foundation time semantic columns.
- **Physical Layout:** Liquid Clustering on `(customer_id)`.
- **Tracked Attributes:** `email_address`, `phone_number`, `address`, `city`, `state`, `country`, `postal_zip_code`.

| Column | Data Type | Role |
|---|---|---|
| `customer_id` | `INT` | Natural entity key |
| `first_name`, `last_name` | `STRING` | Personal identity attributes |
| `email_address`, `phone_number` | `STRING` | Contact coordinates (tracked for Type 2 changes) |
| `address`, `city`, `state`, `country`, `continent` | `STRING` | Location attributes (tracked for Type 2 changes) |
| `postal_zip_code` | `STRING` | Conformed postal identifier |
| `gender` | `STRING` | Demographics |
| `effective_from_ts` | `TIMESTAMP` | Start timestamp of this version (`__START_AT` from `_batch_ts`) |
| `effective_to_ts` | `TIMESTAMP` | Superseded timestamp of this version (`__END_AT`); `NULL` while current |
| `is_current` | `BOOLEAN` | `true` for the active version; `false` for historical versions |

---

### 2.3 `silver.franchises` (Dimension Table with Soft Delete & Time Zone)
- **Source:** `bakehouse_dev.bronze.franchises` joined with `bakehouse_dev.bronze.franchise_time_zones`.
- **Delivery:** Materialized View with windowed cross-batch soft delete tracking.
- **Physical Layout:** Liquid Clustering on `(franchise_id)`.

| Column | Data Type | Transformation Logic / Role |
|---|---|---|
| `franchise_id` | `INT` | Renamed from `franchiseID` |
| `name`, `city`, `district`, `zipcode`, `country`, `size` | `STRING` | Franchise attributes |
| `longitude`, `latitude` | `DOUBLE` | Geospatial coordinates |
| `supplier_id` | `INT` | Renamed from `supplierID` |
| `time_zone` | `STRING` | Joined from `franchise_time_zones` reference seed (IANA name, e.g. `America/New_York`) |
| `is_deleted` | `BOOLEAN` | `true` when absent from the latest snapshot batch; `false` when active |
| `_changed_at` | `TIMESTAMP` | Batch timestamp when current state or deletion was detected |

---

### 2.4 `silver.suppliers` (Dimension Table with Flag Cast & Soft Delete)
- **Source:** `bakehouse_dev.bronze.suppliers`.
- **Delivery:** Materialized View with windowed cross-batch soft delete tracking.
- **Physical Layout:** Liquid Clustering on `(supplier_id)`.

| Column | Data Type | Transformation Logic / Role |
|---|---|---|
| `supplier_id` | `INT` | Renamed from `supplierID` |
| `name`, `ingredient`, `continent`, `city`, `district`, `size` | `STRING` | Supplier profile attributes |
| `longitude`, `latitude` | `DOUBLE` | Geospatial coordinates |
| `is_approved` | `BOOLEAN` | Converted from `'Y'/'N'` via `upper(trim(approved)) == 'Y'` |
| `is_deleted` | `BOOLEAN` | `true` when absent from latest snapshot; `false` when active |
| `_changed_at` | `TIMESTAMP` | Batch timestamp when status was updated or removed |

---

## 3. Physical Layout Strategy (Liquid Clustering)

In accordance with *Lecture - Silver Performance Tuning*:
- **No Over-Partitioning:** Our datasets range from dozens of rows to thousands of rows (kilobytes to megabytes). Fixed partitioning (`PARTITIONED BY`) requires partitions well above 1GB to prevent metadata explosion and small-file fragmentation. Partitioning here is explicitly an anti-pattern.
- **Liquid Clustering Default:** All Silver tables leverage Liquid Clustering (`CLUSTER BY`). Databricks automatically optimizes data layout across incremental writes with zero cardinality traps.
- **Validation Evidence:** Query profiles and `EXPLAIN` execution plans must confirm predicate pushdown on cluster keys.

---

## 4. Acceptance Criteria (Gate G4)

| Test ID | Assertion Description | Target |
|---|---|---|
| **H-T1** | Customer current state invariant | Exactly 1 `is_current = true` row per `customer_id` |
| **H-T2** | Type 2 interval integrity | Half-open intervals: `effective_to_ts` equals next `effective_from_ts`; no gaps or overlaps |
| **H-T3** | Version count reconciliation | Total version count matches base customers + synthetic evolution batches |
| **H-T4** | Supplier soft delete and reactivation | Missing supplier flagged `is_deleted = true`; reappearing supplier flagged `is_deleted = false` |
| **H-T5 / K-T3** | Transaction key uniqueness | Exactly 0 duplicate `transaction_id`s in `silver.transactions` (3,330 distinct rows) |
| **K-T4** | Open version timestamp rule | `effective_to_ts IS NULL` if and only if `is_current = true` |
| **K-T6** | Strict timestamp data typing | All timestamp columns are `TIMESTAMP`; none are `STRING` |
| **PCI-T1** | Card payment minimisation | `cardNumber` absent; `payment_card_last_four` 100% populated |
| **FLAG-T1** | Explicit boolean flag | `silver.suppliers.is_approved` is `BOOLEAN` |
