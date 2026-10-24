# 02 · Data Design – Keys and Time Semantics

| | |
|---|---|
| **Phase** | 2 – Foundation & Kickoff |
| **Lesson** | Lecture – Data Design: Keys and Time Semantics |
| **Status** | DRAFT – key checks are waiting for real data |
| **Planning only** | No tables are created by this document |
| **Traces to** | [scoping_document.md](../01_discovery_scoping/scoping_document.md) §5, [04_ingestion_historization_decisions.md](../01_discovery_scoping/04_ingestion_historization_decisions.md), [03_governance_constraints.md](../01_discovery_scoping/03_governance_constraints.md) |
| **Changes earlier documents** | Yes: change log CL-1 and CL-2 in the scoping document |

> **(VERIFY)** marks items to check against the real data. **(TBC)** marks items confirmed in later phases.

---

## 1. Decisions in this lesson

Decisions **D-xx** (asked) were made by you. Decisions **P-xx** (proposed) are mine, with the rationale.

| ID | Decision | Choice | Source | Rationale |
|---|---|---|---|---|
| D-K1 | Timestamp format in the landed CSVs | **ISO 8601 with an explicit UTC offset**, for example `2024-05-01T13:45:00Z` | Asked | We produce the files, so each value is an unambiguous instant. No `TIMESTAMP_NTZ` is needed anywhere in this build |
| D-K2 | What sets `effective_from_ts` (and the change time on soft-delete tables) | The **batch extract timestamp, taken from the landed file name** | Asked | No source has an `update_ts`. The file name is deterministic, so a replay produces the same history |
| D-K3 | Franchise time zones | A hand-made **seed file** keyed by `franchise_id` with IANA zone names, as an explicit scope addition (CL-1) | Asked | Local business dates need a zone and Bakehouse franchises probably have none (VERIFY) |
| D-K4 | Column naming | **Snake_case from Silver onward.** Bronze keeps the source names as landed. A data dictionary maps source name to Silver name | Asked | Bronze stays traceable to the source. Silver and Gold get one clean convention |
| P-K1 | Type 2 table key | The natural key `(customer_id, effective_from_ts)`. No surrogate key | Proposed | One entity gets history, so a surrogate adds complexity without a consumer need |
| P-K2 | Pipeline columns | `_ingested_at`, `_batch_ts`, `_source_file` on every Bronze table | Proposed | See §3. `_batch_ts` implements D-K2. `_source_file` gives lineage for replay and erasure |
| P-K3 | Interval convention for Type 2 | **Half-open** `[effective_from_ts, effective_to_ts)`. The old version's end equals the new version's start | Proposed | No gaps and no overlaps, which test H-T2 from lesson 4 checks |
| P-K4 | Start of history | The first version of each customer starts at the **first batch's `_batch_ts`**. No sentinel date such as 1900-01-01 | Proposed | The lesson says NULL and not a magic date for the open end. The same logic applies to the start |
| P-K5 | Time zone of the session | `UTC`, set explicitly in the pipeline and warehouse configuration (VERIFY that serverless allows it) | Proposed | Lesson standard. Removes daylight-saving ambiguity |
| P-K6 | Dimension file names | `<source>_<yyyymmddHH>.csv` in UTC, with `HH = 00` for daily dimension files | Proposed | Keeps the lesson 2 naming convention for every source |

---

## 2. Unique keys

Every entity has exactly one documented key. A key-like name is not evidence, so every row below needs the distinct-count check on the real data.

| Entity | Source key | Silver key (D-K4) | Expected result | Verified |
|---|---|---|---|---|
| Customer | `customerID` | `customer_id` | Distinct count = row count, no NULLs | ☐ VERIFY |
| Franchise | `franchiseID` | `franchise_id` | Distinct count = row count, no NULLs | ☐ VERIFY |
| Supplier | `supplierID` | `supplier_id` | Distinct count = row count, no NULLs | ☐ VERIFY |
| Transaction | `transactionID` | `transaction_id` | Distinct count = row count, no NULLs | ☐ VERIFY |
| Time zone seed | `franchiseID` | `franchise_id` | One row per franchise, every franchise covered | ☐ when created |

> [!NOTE]
> The lesson's key table says "verified in Phase 1 profiling". In our Phase 1 the profiling numbers are still VERIFY, so these checks are **not done yet**. Run them in the workspace before Bronze is built.

### Where each key must be unique

A key is unique **in the source snapshot**. After loading, uniqueness depends on the layer and the strategy:

| Table | Unique on | Reason |
|---|---|---|
| Bronze transactions | Not enforced | Bronze is raw. The injected duplicate (lesson 4 §5) must be visible here |
| Bronze dimensions | `(key, _batch_ts)` | Full reload + append means one copy per daily load |
| Silver transactions | `transaction_id` | Deduplicated |
| Silver customers (Type 2) | `(customer_id, effective_from_ts)`, and exactly one `is_current = true` per `customer_id` | P-K1 |
| Silver suppliers, franchises | `supplier_id`, `franchise_id` | Current state with soft delete |
| Gold | Defined with each output in Phase 5 | |

The keys drive the merge condition, deduplication, validation checks and Type 2 logic.

---

## 3. Three kinds of time

| Semantic | Column | Set by | Used for | In this build |
|---|---|---|---|---|
| **Event time** | `transaction_ts` (from the source `dateTime`) | Source | Business analysis, aggregation windows | Yes |
| **Update time** | `update_ts` from the source | Source | Incremental CDC high-water marks | **Not available.** No source has one (lesson 4 §2). CDC was rejected |
| **Arrival time** | `_ingested_at` | Pipeline | Load lineage, replay, freshness SLAs | Yes |
| *Batch time (our addition)* | `_batch_ts` | Parsed from the file name | Stand-in for update time: when a change was first visible in an extract | Yes |

### Why `_batch_ts` exists
- Without a source `update_ts`, something has to date a change in history. `_ingested_at` changes whenever the pipeline re-runs, so a replay would rewrite the history dates.
- `_batch_ts` comes from the file name, so the same file always yields the same date.
- It is **not** an update time. It is the first extract in which a change was visible, so the real change may have happened earlier. This is documented as a known limitation of snapshot ingestion.

### Roles
| Column | Role |
|---|---|
| `_batch_ts` | Sets `effective_from_ts` in Type 2 and `_changed_at` in soft-delete tables |
| `_ingested_at` | Lineage and freshness. Freshness is measured as the Gold refresh time minus the `_ingested_at` of the latest batch |
| `transaction_ts` | All business windows and the as-at join to customers |

In the lab, batches are replayed at a later wall-clock time than their `_batch_ts` (a simulated clock). That is why freshness uses `_ingested_at` and not `_batch_ts`.

---

## 4. Type 2 columns

Applied to Silver customers, and to any later historized table.

| Column | Type | Meaning |
|---|---|---|
| `effective_from_ts` | TIMESTAMP | `_batch_ts` of the batch in which this version first appeared |
| `effective_to_ts` | TIMESTAMP | `_batch_ts` of the batch in which it was superseded. **NULL while current** |
| `is_current` | BOOLEAN | `true` for the open version only |

### Soft-delete columns (suppliers, franchises)
| Column | Type | Meaning |
|---|---|---|
| `is_deleted` | BOOLEAN | `true` when the row is missing from the latest snapshot |
| `_changed_at` | TIMESTAMP | `_batch_ts` of the batch in which the latest change or deletion was detected |

### Rules
- The open version uses **NULL**, not a magic date.
- Intervals are half-open (P-K3). When a version is superseded, its `effective_to_ts` equals the new version's `effective_from_ts`.
- The as-at join from a transaction to a customer version is:
  `transaction_ts >= effective_from_ts AND (effective_to_ts IS NULL OR transaction_ts < effective_to_ts)`.
- **Start of history (P-K4):** the first batch carries no earlier history. A transaction older than a customer's first version would not match. To avoid this, **dimension batch 1 must have a `_batch_ts` at or before the earliest `transaction_ts`**. This is added to the synthetic change plan as a requirement, with test K-T8.

---

## 5. Timestamp standards

| Standard | Rule for this build |
|---|---|
| Storage type | `TIMESTAMP`, holding UTC instants. `TIMESTAMP_NTZ` is **not used**, because no source holds a zone-less wall-clock value (D-K1) |
| Session time zone | `UTC` (P-K5) |
| Landed format | ISO 8601 UTC with `Z`, for example `2024-05-01T13:45:00Z` (D-K1) |
| Parsing | Explicit format string at the Bronze/Silver boundary. Bronze keeps the landed text and Silver parses it (confirmed in Phase 3). No implicit casts |
| Date grain | `DATE` columns are derived in Silver and Gold and never stored as strings |

### Date columns
| Column | Layer | Derivation |
|---|---|---|
| `transaction_date_utc` | Silver | `DATE` of `transaction_ts` in UTC |
| `business_date_local` | Gold | `DATE` of `transaction_ts` converted to the franchise's IANA time zone |

### Local business time and the time zone seed (D-K3)

Franchises span many time zones. Local time is a presentation concern, so storage stays UTC and local dates are derived in Gold.

| Item | Design |
|---|---|
| File | `franchise_time_zones` (Bronze), landed in the Volume like the other extracts |
| Columns | `franchise_id`, `time_zone` (IANA name, for example `Europe/London`) |
| Size | One row per franchise, about 48 (VERIFY) |
| Classification | **Internal**. No personal data |
| Maintenance | Hand-made once by us from the franchise city, country and coordinates. Changes are documented in the approvals log |
| Silver | Joined into Silver franchises as the `time_zone` attribute |
| Known limitation | Silver franchises is current-state, so the **current** zone applies to all historical transactions. That is acceptable, since a franchise doesn't move |
| Failure case | A transaction whose franchise has no zone gets a NULL `business_date_local` and fails test K-T7. It is not silently defaulted to UTC |

> [!IMPORTANT]
> The seed is a **scope addition** to the Phase 1 agreement. It is logged as CL-1 in the scoping document and added to the approvals log, and it needs customer approval.

---

## 6. Source-to-Silver column mapping (keys and time only)

The full data dictionary comes with the Silver design in Phase 4.

| Source column | Silver column | Type | Notes |
|---|---|---|---|
| `customerID` | `customer_id` | key | |
| `franchiseID` | `franchise_id` | key | Also in transactions |
| `supplierID` | `supplier_id` | key | Also in franchises |
| `transactionID` | `transaction_id` | key | |
| `dateTime` | `transaction_ts` | TIMESTAMP | Event time, UTC |
| *(none)* | `_ingested_at`, `_batch_ts`, `_source_file` | TIMESTAMP, TIMESTAMP, STRING | Added in Bronze |

---

## 7. Acceptance tests (feed the definition of done)

| # | Test | Phase |
|---|---|---|
| K-T1 | For each of the four source entities, distinct key count = row count and no NULL keys. Rerun when a source lands | Before Bronze |
| K-T2 | The seed has one row per franchise, and every `time_zone` is a valid IANA name | Bronze |
| K-T3 | Silver transactions: `transaction_id` is unique | Silver |
| K-T4 | Silver customers: one `is_current = true` row per `customer_id`, `effective_to_ts IS NULL` exactly when `is_current` | Silver |
| K-T5 | No Type 2 gaps or overlaps (each `effective_to_ts` equals the next `effective_from_ts`) | Silver |
| K-T6 | All timestamp columns are `TIMESTAMP`, none are strings, and no implicit casts appear in the code | Silver, review |
| K-T7 | No transaction has a NULL `business_date_local` | Gold |
| K-T8 | The first dimension batch's `_batch_ts` is at or before the earliest `transaction_ts` | Bronze |
| K-T9 | `_ingested_at`, `_batch_ts` and `_source_file` are populated on every Bronze row | Bronze |
| K-T10 | A replay of the same files produces identical `effective_from_ts` and `effective_to_ts` values | Silver |

## 8. Impact on other documents

| Document | Change |
|---|---|
| Scoping document | CL-1 (seed, Bronze estimate 4 → 5) and CL-2 (column names) |
| [04_ingestion_historization_decisions.md](../01_discovery_scoping/04_ingestion_historization_decisions.md) | Column names updated. The synthetic change plan must keep dimension batch 1 at or before the earliest transaction (K-T8) |
| [03_governance_constraints.md](../01_discovery_scoping/03_governance_constraints.md) | Approvals log A9: the seed file |
| Table budget | Bronze 5, Silver 4, Gold 3, still within 10 per layer |

## 9. Open items

- [ ] **Run the key checks (K-T1) in the workspace** and send me the results.
- [ ] VERIFY the real type and format of `dateTime`, and that Bakehouse franchises have no time zone column.
- [ ] VERIFY that serverless allows setting the session time zone to UTC.
- [ ] Create the time zone seed and have the customer approve CL-1.
- [ ] Choose the customer columns that trigger a new Type 2 version (from lesson 4, still TBC).
