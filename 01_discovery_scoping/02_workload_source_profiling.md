# 02 · Workload and Source Profiling

| | |
|---|---|
| **Phase** | 1 – Discovery & Scoping |
| **Lesson** | Workload and Source Profiling |
| **Status** | DRAFT – pending customer sign-off |
| **Planning only** | No platform code is built in this phase |
| **Builds on** | [01_use_case_scope.md](01_use_case_scope.md) |

> Items marked **(VERIFY)** are values taken from memory or estimated. They must be measured in the workspace (for example `DESCRIBE DETAIL` or `COUNT(*)` on `samples.bakehouse`) before sign-off. Items marked **(TBC)** are confirmed in later Discovery lessons.

---

## 1. Decisions in this lesson

Decisions **D-xx** (asked) were made by you. Decisions **P-xx** (proposed) are mine, with the rationale.

| ID | Decision | Choice | Source | Rationale |
|---|---|---|---|---|
| D-01 | Workload numbers | Use the lesson's customer numbers as the stated requirement, plus a "Free Edition reality check" column | Asked | Keeps the engagement realistic while being honest about what can be demonstrated on one small warehouse |
| D-02 | Delivery cadence | POS hourly. CRM, suppliers and franchises daily | Asked | Matches the lesson's POS example. Dimensions change slowly and don't need hourly loads |
| D-03 | File layout | Few, larger files per interval: one file per source per batch | Asked | Avoids the small-file problem. A simulated bad case is documented for contrast (§6) |
| D-04 | Growth scenario | 5% per month steady, 22:00 burst, 4x holiday peak, 50 new franchises next quarter | Asked | Uses the lesson's examples, so every growth signal in §4 is covered |
| P-01 | File format | **CSV, uncompressed**, for all four sources | Proposed | See below |
| P-02 | Compression | None for the extracts | Proposed | See below |
| P-03 | Sizing basis | Size the design for the **+12-month peak (≈7x today)**, not today's volume | Proposed | The lesson says "size for +12 months, not today" |
| P-04 | Bandwidth check | Marked N/A for the lab. The production check stays in the checklist | Proposed | The export happens inside the workspace, so there is no network transfer to measure |
| P-05 | Region alignment | Accept the Free Edition region, and record it as a fact (VERIFY) | Proposed | Free Edition fixes the region, so co-location is automatic. We only document it |
| P-06 | Runtime target | Target at most 25% of the interval (the flag threshold is 50%) | Proposed | Leaves headroom for growth and retries before the 50% flag trips |
| P-07 | Hourly schedule on Free Edition | Design for hourly. In the lab, run on a reduced or manual trigger | Proposed | Hourly serverless runs may exhaust the daily quota (§3) |

**Why CSV, uncompressed (P-01, P-02)**
- Lesson 1 allows CSV or Parquet. CSV is the typical legacy POS and CRM extract.
- It forces explicit schema handling in Bronze, because schema inference on CSV is more fragile than on Parquet. That makes it a better learning case.
- At KB-to-MB volumes, splittability and read parallelism are irrelevant, so gzip adds nothing.
- At production volume we would ask upstream for Parquet with snappy compression, or gzip CSV in files sized for parallel reads. This goes in the backlog.

---

## 2. Workload profiling: personas and concurrency

Personas here describe **access patterns**. The named business personas from lesson 1 are mapped to them but remain **(TBC)**.

| Persona | Access pattern | Concurrency today | Concurrency +12 months | Free Edition reality check |
|---|---|---|---|---|
| Operations dashboard (≈ franchise ops manager) | Scheduled refresh, fixed queries | 1 refresh, many viewers | Same pattern, more viewers | Feasible: one refresh on a single warehouse |
| Franchise analysts (≈ BI analyst, procurement analyst) | Ad-hoc SQL, filters and joins | 5 concurrent | 20 concurrent | Not demonstrable at 5 or 20. Validate with a scripted multi-query test and extrapolate |
| Data engineers | Pipeline development and runs | 2-3 | 5 | Limited to 1 user, so only simulated |
| Applications / APIs | Point lookups on Gold | Low | Medium, bursty | Feasible for low volume only. Bursty load is not tested |

### Likely filter and join columns (hypotheses, VERIFY against the schemas)

These drive the clustering and layout decisions in later phases.

| Persona | Filters | Joins |
|---|---|---|
| Operations dashboard | date/time, `franchiseID`, country/city | `franchiseID` |
| Franchise analysts | date/time, product, `franchiseID`, `customerID`, country | `franchiseID`, `customerID`, `supplierID` |
| Applications / APIs | `transactionID`, `customerID` | `customerID` |

> [!NOTE]
> Concurrency numbers are the engagement's stated requirement (D-01). They are not a claim about what Free Edition can serve.

---

## 3. Run periodicity and the 50% rule

Rule: flag any workload where **runtime ≥ 50% of the interval**. The runtimes below are placeholders until the pipeline exists. Measured values replace them in the Bronze and Silver phases.

| Workload | Interval | Flag at (≥50%) | Target (P-06, ≤25%) | Estimated runtime (VERIFY) | Status |
|---|---|---|---|---|---|
| POS ingestion and Bronze→Silver→Gold | 1 hour | 30 min | 15 min | Minutes, given the tiny volume | OK (provisional) |
| CRM refresh | 24 h | 12 h | 6 h | Minutes | OK (provisional) |
| Supplier refresh | 24 h | 12 h | 6 h | Minutes | OK (provisional) |
| Franchise refresh | 24 h | 12 h | 6 h | Minutes | OK (provisional) |

### Risks flagged
| # | Risk | Mitigation |
|---|---|---|
| R1 | **Serverless startup time and the daily quota.** 24 hourly runs a day may consume the Free Edition quota (VERIFY the limit), even though each run is small | Run hourly only for short test windows. Otherwise use a manual or reduced trigger and document it |
| R2 | **Runtime grows 7x or more at the holiday peak**, so a run that takes 5 minutes today may take far longer | Re-test the 50% rule with scaled-up data. Prefer incremental processing |
| R3 | **Overlapping runs** if the 22:00 burst delays an hourly run | Limit concurrent runs and queue them. Throttle ingest |

---

## 4. Growth and scaling implications

All growth figures are **simulated** (D-04), because Bakehouse is static sample data.

| Signal | Scenario | Design implication |
|---|---|---|
| Steady growth | Transactions +5% per month | 1.05¹² ≈ **1.8x** in 12 months. Size for +12 months (P-03) |
| Bursty arrival | End-of-day uploads cluster at 22:00 | Autoscaling compute and throttled ingest. On Free Edition, a design note only |
| Seasonal peak | Holiday trading is 4x | Load test at peak before go-live |
| New-market rollout | 50 new franchises next quarter | Table budget and SLA review is triggered. The franchise count grows from about 48 to about 98 (VERIFY) |

### Sizing envelope
| Case | Multiplier on today's volume |
|---|---|
| Today | 1x |
| +12 months, steady | ≈ 1.8x |
| +12 months at holiday peak | ≈ 1.8 × 4 ≈ **7.2x** (design target, P-03) |
| Stress case: peak plus new-market (franchises ≈ 2x) | ≈ 7.2 × 2 ≈ **14-15x** (upper bound, tested only if time allows) |

The stress case is probably double counting, since the 5% growth may already include new franchises. I treat it as an upper bound, not a requirement.

---

## 5. Source data profiling

### 5.1 Inventory

Row counts are approximate recollections of the sample dataset **(VERIFY)**. Sizes are estimates.

| Source | Bakehouse table | Format (P-01) | Compression (P-02) | Approx. rows (VERIFY) | Est. size (VERIFY) | Cadence (D-02) |
|---|---|---|---|---|---|---|
| POS | `sales_transactions` | CSV | None | ~3,300 | < 1 MB | Hourly batch |
| CRM | `sales_customers` | CSV | None | ~300 | < 100 KB | Daily |
| Suppliers | `sales_suppliers` | CSV | None | ~30 | < 10 KB | Daily |
| Franchises | `sales_franchises` | CSV | None | ~50 | < 20 KB | Daily |

At the +12-month peak (7.2x), the total is still only a few MB. Volume is not a sizing constraint in this lab, so the profile shows the method and the growth assumptions, not real load.

### 5.2 File layout and arrival (D-03)

| Attribute | Value |
|---|---|
| Naming convention | `<source>/<yyyy>/<mm>/<dd>/<source>_<yyyymmddHH>.csv`, a proposal (TBC) |
| POS | One file per hourly batch, cut by transaction timestamp. The number of batches is set once the time range is profiled |
| Dimensions | One full-extract file per day |
| Files per interval | 1 per source |

### 5.3 Field-level observations (VERIFY)
- `sales_transactions` is expected to hold payment details, including a card number. This is likely **PII or sensitive data**, so it is carried into the governance lesson.
- `sales_customers` holds names, email and phone, so it is **PII**.
- `sales_franchises` references `supplierID`, which links franchises to suppliers.

---

## 6. Small-file check

The risk is the **number of files** per interval, because per-file open costs dominate when there are thousands of small files. The extract files here are small in bytes, but there are very few of them.

| Check | Working threshold (TBC) | Result for this design |
|---|---|---|
| Files per source per interval | Flag if there are more than about 100 | 1 → **pass** |
| Median and p95 file size | Production target: hundreds of MB. Flag many files well below that | Tiny data, but 1 file per interval, so **pass** |

**Documented bad case (for contrast):** if POS exported one file per transaction, a day of data would be about 3,300 files of about 0.3 KB each. This would be flagged. The fix order would be:
1. Push upstream for fewer, larger extracts per interval.
2. Fall back to compaction on the Databricks side (Bronze phase).

---

## 7. Extraction, bandwidth, and region alignment

| Check | Lab status | Production check kept |
|---|---|---|
| Extraction method validated | The export from `samples.bakehouse` to CSV in the Volume works at the agreed cadence | ☐ |
| Bandwidth measured | N/A (P-04). Everything stays inside the workspace | ☐ Measure transfer window against the run interval |
| Region alignment | Workspace, Volume and managed storage in the same region by default (P-05) | ☐ Record the region (VERIFY) |
| Compute/storage co-location | Serverless compute and storage are in the same region, so there are no cross-region reads | ☐ |

---

## 8. Impact on the definition of done and scope

- Adds a validation need: a **50% rule check** on measured runtimes.
- Adds a risk to the register: the **Free Edition quota** against the hourly schedule (R1).
- No change to the table budget. Confirmation of the 4/4/3 estimate waits for the governance and decision lessons.
- Raw sources are unchanged, and the source list from lesson 1 still stands.

## 9. Open items

- [ ] VERIFY row counts, sizes, schemas and time range in `samples.bakehouse`.
- [ ] VERIFY the Free Edition serverless quota and the workspace region.
- [ ] Cut the final batch plan for POS once the time range is known.
- [ ] Confirm the working small-file thresholds.
- [ ] Carry the PII findings into the governance lesson.

## References
- [Medallion architecture](https://docs.databricks.com/aws/en/lakehouse/medallion)
- [What is a data lakehouse?](https://docs.databricks.com/aws/en/lakehouse/)
