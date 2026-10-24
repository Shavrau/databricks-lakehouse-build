# 04 · Ingestion Mode and Historization Decisions

| | |
|---|---|
| **Phase** | 1 – Discovery & Scoping |
| **Lesson** | Governance Readiness and Design Decisions (part 2 of 2: design decisions) |
| **Status** | DRAFT – pending customer sign-off |
| **Planning only** | No platform code is built in this phase |
| **Builds on** | [02_workload_source_profiling.md](02_workload_source_profiling.md), [03_governance_constraints.md](03_governance_constraints.md) |
| **Drives** | Bronze design (Phase 3) and Silver design (Phase 4) |

> These two decisions are the hardest to change later. Changing them means a re-design of Bronze and Silver.

---

## 1. Decisions in this lesson

Decisions **D-xx** (asked) were made by you. Decisions **P-xx** (proposed) are mine, with the rationale.

| ID | Decision | Choice | Source |
|---|---|---|---|
| D-I1 | Ingestion mode, POS (`sales_transactions`) | **Snapshot + simulated loads** | Asked |
| D-I2 | Ingestion mode, dimensions (customers, suppliers, franchises) | **Full reload + append** with `_ingested_at` | Asked |
| D-H1 | Historization | **Type 2 SCD for customers.** Soft delete and current state for suppliers and franchises. Transactions are append-only facts | Asked |
| D-H2 | Synthetic changes | Inject a small, documented set of changes into later dimension batches | Asked |
| P-I1 | No synthetic `update_ts` column is added to the extracts | Proposed | |
| P-H1 | Customer columns tracked for Type 2 (see §3) | Proposed | |
| P-H2 | Transactions deduplicated on `transactionID`, with no historization | Proposed | |
| P-H3 | Time Travel allowed only for audit and repair (§4) | Proposed | |

---

## 2. Ingestion mode (per source)

### 2.1 Walking the decision tree

| Source | Q1: change events or a reliable update timestamp? | Q2: small enough to reload in full each run? | Result |
|---|---|---|---|
| `sales_transactions` | **No.** `dateTime` is event time, not change time | Yes at lab size (about 3,300 rows), but see below | **Snapshot + simulated loads** (D-I1) |
| `sales_customers` | **No** (VERIFY there is no update column) | Yes (about 300 rows) | **Full reload + append** (D-I2) |
| `sales_suppliers` | **No** | Yes (about 30 rows) | **Full reload + append** (D-I2) |
| `sales_franchises` | **No** | Yes (about 50 rows) | **Full reload + append** (D-I2) |

**Why POS is not "full reload" even though it is small.** Applied to the lab data alone, the tree would say *reload*. The engagement is sized for production behaviour: hourly drops, 5% monthly growth and a 7.2x peak (lesson 2). An append-only fact table reloaded in full each hour would duplicate every row 24 times per day and the cost would grow with history. So we load an initial full snapshot and then replay batches, which is how the production pipeline would behave.

**Why CDC was rejected (P-I1).** No source has a reliable update timestamp, and adding a synthetic one would invent a capability the real source doesn't have. That would make the design look more mature than it is.

### 2.2 What each mode means for the build

| Source | Mode | Bronze behaviour (Phase 3) | Trade-off accepted |
|---|---|---|---|
| POS | Snapshot + simulated loads | First batch is the full snapshot, then hourly batches replayed in file arrival order | More data movement. Simple and testable |
| Customers, suppliers, franchises | Full reload + append | Each daily file is appended with an `_ingested_at` | Bronze grows by one full copy per load (about 300 rows per day for customers), which is trivial and controlled by the 90-day Bronze retention |

Silver detects changes in the dimensions by **comparing snapshots** between loads (Phase 4). The Databricks AUTO CDC snapshot API is the likely tool **(VERIFY it is available on Free Edition)**.

---

## 3. Historization strategy (per entity)

| Entity | Strategy | Why |
|---|---|---|
| `customers` | **Type 2 SCD** | Marketing needs historical customer attributes ("as at" analysis), as stated in the lesson |
| `suppliers` | **Soft delete** + current state | Consumers need the current supplier list and to know when one is removed. No "as at" need was raised |
| `franchises` | **Soft delete** + current state | Same reasoning as suppliers |
| `transactions` | **Append-only fact, no historization** (P-H2) | A transaction is an event and doesn't change. Duplicates are removed on `transactionID` |

### Type 2 design for customers (implemented in Phase 4)

| Item | Design |
|---|---|
| Key | `customerID` |
| Version columns | `effective_from_ts`, `effective_to_ts`, `is_current` (names and types fixed in [Phase 2, lesson 2](../02_foundation_kickoff/02_data_design_keys_time.md)) |
| Tracked columns (P-H1, TBC) | email_address, phone_number, address, city, state, country, postal_zip. These are the attributes marketing would analyse "as at" a date |
| Untracked columns | Overwritten in place without a new version |
| Invariants to test | Exactly one `is_current = true` row per customer. No overlapping or gapped intervals per customer |

### Soft delete design for suppliers and franchises

| Item | Design |
|---|---|
| Columns | `is_deleted`, `_changed_at` (time of the batch in which the change was detected, see [Phase 2, lesson 2](../02_foundation_kickoff/02_data_design_keys_time.md)) |
| Rule | A row missing from a later snapshot is flagged `is_deleted = true` and **not physically removed** |
| Invariants to test | A deleted supplier remains queryable and flagged. A supplier that reappears is flagged active again |

### Interaction with governance

Type 2 keeps old personal data (previous emails and addresses). The erasure procedure in [03_governance_constraints.md](03_governance_constraints.md) §3 must therefore delete **every version** of a customer. This is a deliberate cost of Type 2 and one reason it is limited to a single entity.

---

## 4. Delta Time Travel is not historization

| Usage | Verdict | Our position (P-H3) |
|---|---|---|
| Audit what a pipeline wrote in an earlier run | Proper | Allowed |
| Repair with `RESTORE TABLE` after a bad write | Proper | Allowed, in the runbook |
| Reproduce a report "as at last quarter" for business users | **Misuse** | Use Type 2 (customers) |
| Satisfy a multi-year regulatory history requirement | **Misuse** | Use explicit tables with retention rules (§4 of lesson 3) |

Why it is not historization:
- Versions are pruned by `VACUUM` and bounded by retention settings (7 days by default here).
- Every write creates a version, including maintenance operations such as OPTIMIZE, so versions don't match business changes.
- It also conflicts with erasure: data that has been "deleted" stays readable in old versions until VACUUM.

---

## 5. Synthetic change plan (D-H2)

Bakehouse is static, so the landed extracts are altered **in the files only**. The sample data in `samples.bakehouse` is never modified. All counts are proposals **(TBC)**.

| Batch | Change | Purpose |
|---|---|---|
| Daily batch 1 | Unchanged snapshot of all dimensions. Its `_batch_ts` must be at or before the earliest `transaction_ts`, so the as-at join always finds a customer version | Baseline |
| Daily batch 2 | About 10 customers change email or address. About 5 new customers | Tests Type 2 versions and inserts |
| Daily batch 2 | 1 supplier is missing from the file | Tests soft delete |
| Daily batch 3 | 1 customer changes again, and the removed supplier reappears | Tests multiple versions and reactivation |
| Daily batch 3 | 1 franchise attribute changes (for example size) | Tests the current-state overwrite |
| Hourly POS batches | Includes one duplicated transaction row | Tests deduplication on `transactionID` |

Every change is listed in a change log kept next to the extract code, so that expected results can be calculated and tested.

---

## 6. Acceptance tests (feed the definition of done)

| # | Test | Phase |
|---|---|---|
| H-T1 | Each customer has exactly one current row | Silver |
| H-T2 | No overlapping or gapped Type 2 intervals | Silver |
| H-T3 | The number of customer versions equals the number of changes in the change log | Silver |
| H-T4 | A removed supplier is flagged `is_deleted` and not removed, and reactivation works | Silver |
| H-T5 | Silver `transactions` has no duplicate `transactionID` | Silver |
| H-T6 | Bronze row count equals the sum of landed file rows for each source | Bronze |
| H-T7 | No business query or table in the pipeline uses `VERSION AS OF` or `TIMESTAMP AS OF` | Review |

## 7. Impact on other documents

- **Table budget:** unchanged (about 4 Bronze, 4 Silver, 3 Gold). Type 2 and soft delete add columns, not tables.
- **Periodicity:** the daily dimension jobs and hourly POS job from lesson 2 still apply.
- **Governance:** the erasure procedure depends on the Type 2 design (§3).

## 8. Open items

- [ ] VERIFY there is no update timestamp in any source schema.
- [ ] VERIFY availability of the AUTO CDC snapshot API on Free Edition.
- [ ] Confirm the Type 2 tracked columns with the marketing persona.
- [ ] Finalise the change plan counts (§5) once the batch plan is cut.

## References
- COPY INTO: [AWS](https://docs.databricks.com/aws/en/ingestion/cloud-object-storage/copy-into/) | [Azure](https://learn.microsoft.com/en-us/azure/databricks/ingestion/cloud-object-storage/copy-into/) | [GCP](https://docs.databricks.com/gcp/en/ingestion/cloud-object-storage/copy-into/)
- AUTO CDC APIs: [AWS](https://docs.databricks.com/aws/en/ldp/cdc) | [Azure](https://learn.microsoft.com/en-us/azure/databricks/ldp/cdc) | [GCP](https://docs.databricks.com/gcp/en/ldp/cdc)
