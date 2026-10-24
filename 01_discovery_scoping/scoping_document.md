# Scoping Document – Bakehouse Lakehouse Build

| | |
|---|---|
| **Customer** | Bakehouse (global cookie franchise) |
| **Phase** | 1 – Discovery & Scoping (exit gate) |
| **Version / status** | v0.1 DRAFT – **not signed off** |
| **Platform** | Databricks Free Edition, serverless |

> This document consolidates lessons 1 to 4. Every later phase must reference it. If a build decision contradicts this document, **either the decision or this document must change, explicitly**. Items marked **(ROLE-PLAY)** are invented for the training engagement. Items marked **(VERIFY)** are unconfirmed.

| Detail source | File |
|---|---|
| Use case and scope | [01_use_case_scope.md](01_use_case_scope.md) |
| Workload and source profiling | [02_workload_source_profiling.md](02_workload_source_profiling.md) |
| Governance | [03_governance_constraints.md](03_governance_constraints.md) |
| Ingestion and historization decisions | [04_ingestion_historization_decisions.md](04_ingestion_historization_decisions.md) |

---

## 1. Pipeline boundaries

### Objective
Stand up the first production lakehouse for Bakehouse: file extracts land in a Unity Catalog Volume and one medallion pipeline produces governed analytics for franchise operations.

### Scope
| Item | Agreed |
|---|---|
| Pipelines | Exactly 1 (Bronze → Silver → Gold) |
| Table budget | At most 10 per layer. Working estimate: Bronze 5, Silver 4, Gold 3 **(TBC)** |
| Sources | `sales_transactions` (POS), `sales_customers` (CRM), `sales_suppliers`, `sales_franchises`, all from `samples.bakehouse`, landed as CSV files. Plus one hand-made reference seed, `franchise_time_zones` (see change log CL-1) |
| Backlog (out of scope) | Reviews and media tables, streaming/Kafka, multi-workspace promotion, further pipelines |

### Working table list (hypothesis, TBC)
| Layer | Tables |
|---|---|
| Bronze | transactions, customers, suppliers, franchises, franchise_time_zones (raw as landed, with `_ingested_at`) |
| Silver | transactions (deduplicated), customers (**Type 2**), suppliers (soft delete), franchises (soft delete, with `time_zone` from the seed) |
| Gold | 3 outputs, matching the consumers below |

### Named consumers (proposed, ROLE-PLAY, needs approval)
| Persona | Gold output (working name) | Based on |
|---|---|---|
| Franchise operations manager | Sales by franchise and day (dashboard) | transactions + franchises |
| BI analyst | Customer sales view, with "as at" customer attributes | transactions + customers (Type 2) |
| Procurement analyst | Franchise-to-supplier view | franchises + suppliers |

---

## 2. SLAs (proposed, ROLE-PLAY, needs approval)

Free Edition offers no platform SLA, so these are engagement targets only.

| Gold output | Freshness target | Availability target | Reasoning |
|---|---|---|---|
| Sales by franchise and day | Within 90 minutes of an hourly POS drop | 99% in business hours (design target) | Hourly interval, plus a run well under 50% of the interval |
| Customer sales view | Within 90 minutes (sales). Customer attributes refreshed daily | 99% in business hours (design target) | Mixed hourly and daily inputs |
| Franchise-to-supplier view | Within 24 hours of the daily extracts | 99% in business hours (design target) | Slow-changing reference data |

---

## 3. Periodicity

| Workload | Interval | 50% flag | Target (25%) | Status |
|---|---|---|---|---|
| POS ingestion and transformation | 1 hour | 30 min | 15 min | OK (provisional) |
| Customers, suppliers, franchises refresh | 24 hours | 12 h | 6 h | OK (provisional) |

### Flagged risks
| # | Risk | Mitigation |
|---|---|---|
| R1 | Hourly serverless runs may exhaust the Free Edition daily quota | Reduced or manual trigger in the lab |
| R2 | Runtime grows with the 7.2x holiday peak | Re-test the 50% rule with scaled data |
| R3 | The 22:00 burst delays an hourly run and overlaps runs | Limit concurrency and throttle ingest |

Sizing basis: **7.2x today's volume** (+12 months at holiday peak).

---

## 4. Governance constraints

| Area | Position |
|---|---|
| Classification | `Internal`, `Restricted`, `Legal Hold`, applied as tags at object creation |
| Restricted columns | Customer names, email, phone, address, postal code, gender, and card number |
| Regulations | Treated as GDPR-style. Restricted columns are tagged in Bronze and Silver, and masked at the Gold consumer boundary (CL-4) |
| Erasure | 30-day target. Deletes from Landing, Bronze, **all Type 2 versions** in Silver, Gold, then VACUUM |
| Card numbers | Dropped or tokenized after Bronze |
| Retention | Landing and Bronze 90 days. Transactions 7 years. Customers relationship end + 24 months **(ROLE-PLAY)** |
| Residency | Stays in the Free Edition region (VERIFY) |
| Third-party tools | None |
| Approvals | Tracked in [03_governance_constraints.md](03_governance_constraints.md) §7 |

---

## 5. Design decisions

| Source | Ingestion mode | Historization | Rationale |
|---|---|---|---|
| `sales_transactions` | Snapshot + simulated loads | Append-only, deduplicated on `transactionID` | No update timestamp. Production-like hourly arrival, so reload would duplicate rows |
| `sales_customers` | Full reload + append | **Type 2 SCD** | No update timestamp. Small. Marketing needs "as at" attributes |
| `sales_suppliers` | Full reload + append | Soft delete, current state | No update timestamp. Small. Only current state and removals matter |
| `sales_franchises` | Full reload + append | Soft delete, current state | Same as suppliers |

Delta Time Travel is used only for audit and repair, never for business history.

---

## 6. Definition of done

| # | Criterion | Evidence |
|---|---|---|
| D1 | Functional pipeline | A pipeline run populates Bronze, Silver and Gold, and a scheduled Job runs it |
| D2 | Data validation | Count, key, time-range and business-rule checks pass, including tests H-T1 to H-T7 in lesson 4 |
| D3 | Unity Catalog schemas | Every object has an owner, comment and classification tag (tests G-T1, G-T2) |
| D4 | Documentation | This document, a runbook and per-persona guides |
| D5 | Scope budget respected | 1 pipeline, and 10 or fewer tables per layer |
| D6 | Governance controls | Gold masks, erasure test passes, no full card numbers in Silver or Gold (tests G-T3 to G-T5) |

D6 is an addition that I made, because governance tests would otherwise have no home in the definition of done. Remove it if you prefer.

---

## 7. Assumptions, constraints and open items

- The sample data is static. Growth, bursts and changes are **simulated**.
- Free Edition limits (quota, concurrency, mask and group support, region) are **(VERIFY)**.
- Row counts, sizes and schemas are **(VERIFY)**, measured before sign-off.
- All ROLE-PLAY values (SLAs, retention, erasure target, personas) need explicit approval.

---

## 8. Change log (changes made after the Phase 1 drafts)

| ID | Date | Change | Reason | Source |
|---|---|---|---|---|
| CL-1 | 2026-10-24 | Added the reference seed `franchise_time_zones` (about 48 rows, one IANA time zone per `franchiseID`) as a fifth landed file. Bronze estimate goes from 4 to 5 tables. The Silver table count is unchanged | Local business dates need a franchise time zone, and Bakehouse franchises probably have none (VERIFY). It is hand-made reference data, not a new source system, and carries no personal data (Internal) | [Phase 2, lesson 2](../02_foundation_kickoff/02_data_design_keys_time.md) |
| CL-2 | 2026-10-24 | Column conventions standardised: `_ingested_at`, `effective_from_ts`, `effective_to_ts`, `is_current`, `_changed_at`. Replaces the earlier working names `ingestion_ts`, `effective_from`, `effective_to` and `updated_at` | One convention across every layer | [Phase 2, lesson 2](../02_foundation_kickoff/02_data_design_keys_time.md) |
| CL-3 | 2026-10-24 | Environments resolved: one catalog per environment (`bakehouse_dev`, `bakehouse_prod`), each with schemas `landing`, `bronze`, `silver`, `gold`. The table budget (10 per layer) is counted in the prod catalog, and dev mirrors it | Replaces "dev/prod separation by catalog or schema (TBC)" from lesson 1 | [Phase 2, lesson 3](../02_foundation_kickoff/03_governance_guardrails.md) |
| CL-4 | 2026-10-24 | Masking is enforced only at the Gold consumer boundary. Bronze and Silver columns are tagged, and card numbers are dropped or tokenized in Silver. Gold has no direct identifiers except one masked customer-detail view | Refines "mask by default" from lesson 3 of Phase 1 | [Phase 2, lesson 3](../02_foundation_kickoff/03_governance_guardrails.md) |

---

## 9. Sign-off (exit gate)

| Role | Name | Decision | Date | Conditions |
|---|---|---|---|---|
| Customer sponsor | ☐ | ☐ Approved ☐ Rejected | ☐ | |
| Customer security / governance | ☐ | ☐ Approved ☐ Rejected | ☐ | |
| Delivery lead | ☐ | ☐ Approved ☐ Rejected | ☐ | |

**Exit criteria:** all sections complete, VERIFY items resolved, sign-offs recorded.
