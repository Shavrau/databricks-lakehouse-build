# 03 · Governance Readiness

| | |
|---|---|
| **Phase** | 1 – Discovery & Scoping |
| **Lesson** | Governance Readiness and Design Decisions (part 1 of 2: compliance) |
| **Status** | DRAFT – pending customer sign-off |
| **Planning only** | No platform code is built in this phase |
| **Builds on** | [01_use_case_scope.md](01_use_case_scope.md), [02_workload_source_profiling.md](02_workload_source_profiling.md) |
| **Continues in** | [04_ingestion_historization_decisions.md](04_ingestion_historization_decisions.md) |

> **(VERIFY)** marks items to check against the real schemas or workspace. **(TBC)** marks items confirmed in later phases. **(ROLE-PLAY)** marks values invented for this training engagement. The customer must approve them as if they were real.

---

## 1. Decisions in this lesson

Decisions **D-xx** (asked) were made by you. Decisions **P-xx** (proposed) are mine, with the rationale.

| ID | Decision | Choice | Source | Rationale |
|---|---|---|---|---|
| D-G1 | Depth of GDPR/CCPA treatment | Treat as GDPR-style. Mask Restricted columns by default and document an erasure procedure that reaches Bronze and Type 2 history | Asked | The customer table has people in several countries. Erasure into Type 2 history is the hardest case, so it's worth designing now |
| P-G1 | Classification scheme | The three lesson tags: `Internal`, `Restricted`, `Legal Hold` | Proposed | The lesson says to agree the scheme during scoping. Three tags are enough for this dataset, and adding more would be over-engineering |
| P-G2 | `customerID` classified **Internal** (pseudonymous join key) | | Proposed | Analysts must join on it. It is still personal data in GDPR terms (it can be linked back), so access controls and the erasure procedure still apply. **The customer must approve this** |
| P-G3 | Third-party tools | **None.** Databricks-native tools only | Proposed | Avoids a legal/security review sign-off and keeps the scope small. Any later tool triggers the review in §6 |
| P-G4 | Data residency | Stay within the workspace region. No cross-region sharing or export | Proposed | Free Edition fixes the region, so it is easy to comply with. It also keeps Delta Sharing out of scope |
| P-G5 | Card number handling | Keep as landed in Bronze (Restricted). **Do not carry full card numbers into Silver and Gold**: drop or tokenize them | Proposed | Data minimisation. No persona in lesson 1 needs the card number |
| P-G6 | Legal Hold | Define the tag and the rule. **No data is held** in the sample | Proposed | Bakehouse has no flagged transaction range, and inventing one adds no value |

---

## 2. Classification of in-scope data

Column lists are from memory of the sample schemas **(VERIFY every column)**.

### `sales_customers` (CRM)
| Column(s) | Tag | Note |
|---|---|---|
| first_name, last_name, email_address, phone_number | **Restricted** | Direct identifiers |
| address, postal_zip | **Restricted** | Precise location |
| gender | **Restricted** | Personal attribute |
| city, state | Internal (TBC) | Coarse location. Revisit if combined with other fields |
| country, continent | Internal | Needed for analysis and residency reporting |
| customerID | Internal (P-G2) | Pseudonymous key |

### `sales_transactions` (POS)
| Column(s) | Tag | Note |
|---|---|---|
| cardNumber | **Restricted** | Payment data (P-G5) |
| customerID | Internal (P-G2) | Links a purchase to a person |
| transactionID, franchiseID, dateTime, product, quantity, unitPrice, totalPrice, paymentMethod | Internal | Business data |

### `sales_franchises` and `sales_suppliers`
All Internal (business locations, product and supplier names). Franchise and supplier contact data are not expected in the sample **(VERIFY)**. If a person's name appears, tag it as Restricted.

> [!IMPORTANT]
> Tags are applied **when objects are created** (Phases 3 to 5), not retrofitted. This table is the source of truth.

---

## 3. GDPR / CCPA obligations

| Obligation | What we capture | Downstream impact |
|---|---|---|
| Columns identifying a person | §2 (Restricted columns) | Mask by default using Unity Catalog column masks, with unmasked access only for an approved group. Free Edition support for masks and groups is **(VERIFY)**. The fallback is masked views |
| Right to erasure | A customer can be erased on request (see below) | Delete across Bronze, Silver (all versions) and Gold. This affects the Type 2 design |
| Data minimisation | Only keep columns a persona needs | Card number is dropped or tokenized after Bronze (P-G5) |
| Storage limitation | Maximum retention per dataset (§4) | Scheduled deletion plus VACUUM |

### Erasure procedure (design, implemented in later phases)

| Layer | Action |
|---|---|
| Landing Volume | Delete or rewrite raw files that contain the person's rows |
| Bronze | Delete rows for the `customerID` |
| Silver `customers` (Type 2) | Delete **every version**, not only the current one |
| Silver `transactions` | Keep the sales facts. Either keep the `customerID` as an orphan key or null it, subject to approval |
| Gold | Recompute any customer-level outputs |
| Storage | Run `VACUUM`, because deleted rows remain readable in older Delta versions until then |

- **ROLE-PLAY target:** erasure completed within **30 days** of the request.
- Delta file retention defaults to 7 days, so physical removal fits inside the target.
- Erasure must be logged, with who requested it, when it was done and who approved it.
- **Conflict rule:** a `Legal Hold` object **cannot be erased** until the hold is released.

---

## 4. Retention

All values are **ROLE-PLAY** and need customer approval.

| Dataset | Minimum | Maximum | Mechanism |
|---|---|---|---|
| Landing files (Volume) | 30 days | 90 days | Scheduled cleanup |
| Bronze tables | 30 days | 90 days | Scheduled delete plus VACUUM |
| Silver `transactions` | 7 years | 7 years | Retention for financial records |
| Silver `customers` (Type 2 history) | Relationship active | Relationship end + 24 months, or on erasure request | Scheduled delete plus VACUUM |
| Silver `suppliers`, `franchises` | While active | Relationship end + 24 months | Scheduled delete |
| Gold | Follows the source | Follows the source | Recompute |
| Delta Time Travel and log | 7 days file retention (default) | 30 days log (default) | VACUUM. Operational use only, never a business retention mechanism (see lesson 4) |

---

## 5. Data residency

| Item | Position |
|---|---|
| Allowed storage and processing region | The Free Edition workspace region (VERIFY and record it) |
| Cross-region or external sharing | Not allowed. Out of scope |
| Customer data subjects | Customers appear in several countries, so assume GDPR-style obligations apply to all of them |

---

## 6. Third-party tools

| Tool | Touches data? | Review needed? | Status |
|---|---|---|---|
| Databricks (UC, serverless compute, Lakeflow pipelines, Jobs, SQL warehouse, dashboards) | Yes | Covered by the platform agreement | Approved (P-G3) |
| Any external BI, orchestration or data-quality tool | Would | **Yes: legal and security sign-off before use** | None planned |

---

## 7. Approvals log

Record written approval for every dependency, storage location and data-handling decision.

| # | Decision | Who approved | Date | Conditions |
|---|---|---|---|---|
| A1 | Classification scheme and column tags (§2) | ☐ | ☐ | |
| A2 | `customerID` as Internal (P-G2) | ☐ | ☐ | |
| A3 | Card number dropped or tokenized after Bronze (P-G5) | ☐ | ☐ | |
| A4 | Retention values (§4) | ☐ | ☐ | |
| A5 | Erasure procedure and 30-day target (§3) | ☐ | ☐ | |
| A6 | Residency position (§5) | ☐ | ☐ | |
| A7 | No third-party tools (§6) | ☐ | ☐ | |
| A8 | Landing zone in a UC Volume (from lesson 1) | ☐ | ☐ | |
| A9 | Scope addition: `franchise_time_zones` seed file, classified Internal (scoping document CL-1) | ☐ | ☐ | |
| A10 | Redaction strategy: no direct identifiers in Gold except one masked customer-detail view, `pii-readers` unmasked (Phase 2, lesson 3) | ☐ | ☐ | |
| A11 | Group ownership model and privilege matrix (Phase 2, lesson 3) | ☐ | ☐ | |
| A12 | Managed volume instead of an external location, due to Free Edition (Phase 2, lesson 3) | ☐ | ☐ | |
| A13 | Catalog layout: `bakehouse_dev` and `bakehouse_prod` (Phase 2, lesson 3) | ☐ | ☐ | |

---

## 8. Acceptance tests (feed the definition of done)

| # | Test | Phase it runs in |
|---|---|---|
| G-T1 | Every Restricted column in Bronze and Silver has the `Restricted` tag, and every Restricted column that reaches Gold is masked (refined in Phase 2, lesson 3) | Governance phase |
| G-T2 | All tables carry a classification tag, owner and comment (queried from `information_schema`) | Governance phase |
| G-T3 | An erasure test customer is removed from Landing, Bronze, Silver (all versions) and Gold | Silver and Gold |
| G-T4 | Full card numbers are absent from Silver and Gold | Silver |
| G-T5 | Retention jobs exist for each dataset in §4 | Operations |

## 9. Open items

- [ ] VERIFY every column list in §2 against the real schemas.
- [ ] VERIFY Free Edition support for column masks, row filters and groups.
- [ ] Customer to approve the ROLE-PLAY values (retention, erasure target, `customerID` classification).
- [ ] Decide the treatment of `customerID` in Silver `transactions` after erasure.

## References
- [Unity Catalog overview](https://docs.databricks.com/aws/en/data-governance/unity-catalog/)
