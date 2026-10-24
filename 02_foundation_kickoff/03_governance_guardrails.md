# 03 · Governance Setup and Guardrails

| | |
|---|---|
| **Phase** | 2 – Foundation & Kickoff |
| **Lesson** | Lecture – Governance Setup and Guardrails |
| **Status** | DRAFT – the checks in §8 are waiting for your workspace |
| **Planning only** | No catalogs, groups, volumes or code are created by this document |
| **Traces to** | [03_governance_constraints.md](../01_discovery_scoping/03_governance_constraints.md), [scoping_document.md](../01_discovery_scoping/scoping_document.md), [02_data_design_keys_time.md](02_data_design_keys_time.md) |
| **Changes earlier documents** | Yes: CL-3 and CL-4 in the scoping document |

> **(VERIFY)** marks items to check against the real workspace. **(DEVIATION)** marks places where Free Edition forces us away from the lesson's standard.

---

## 1. Decisions in this lesson

Decisions **D-xx** (asked) were made by you. Decisions **P-xx** (proposed) are mine, with the rationale.

| ID | Decision | Choice | Source | Rationale |
|---|---|---|---|---|
| D-S1 | Redaction at the Gold boundary | Gold has **no direct identifiers by default**. One Gold customer-detail view exposes them **masked**, and `pii-readers` see them unmasked | Asked | Minimal, and it makes masking testable |
| D-S2 | Row-level filtering in Gold | **None** | Asked | No persona in the scoping document needs restricted rows. Added only if the customer asks |
| D-S3 | Groups | Check whether groups can be created in your workspace. If yes, create them. If not, document the model and name your user as interim owner | Asked | Free Edition is single-user |
| D-S4 | Code structure | **IDE / bundle-first**: source in this repo, deployed with Declarative Automation Bundles | Asked | The project is already a local repo, and the structure is CI/CD ready |
| D-S5 | Catalog layout | **One catalog per environment** (`bakehouse_dev`, `bakehouse_prod`), each with schemas `landing`, `bronze`, `silver`, `gold` | Asked | Settles the dev/prod separation that Phase 1 left TBC. Bundle targets map to catalogs |
| P-S1 | Enforcement point | Masking logic lives **only at the Gold consumer boundary**, never inside ETL code | Proposed | The lesson's rule. Scattered masking is hard to audit and easy to bypass |
| P-S2 | Group names | Hyphenated, as in the lesson: `platform-admins`, `data-engineers`, `data-consumers`, `pii-readers`, `ingestion-writers` | Proposed | One naming style. The first four match the lesson and your answers |
| P-S3 | Landing volume type | A **managed volume** in catalog managed storage (DEVIATION from the lesson's external location) | Proposed | Free Edition can't use your own bucket (VERIFY). See §5 |
| P-S4 | Table budget counting | The 10-per-layer budget is counted in the **prod catalog**. Dev mirrors it | Proposed | Counting both would double the number with no change in scope (CL-3) |
| P-S5 | Classification tags | Applied to columns in **Silver (required) and Bronze** | Proposed | The same restricted columns land in Bronze, and tags are cheapest at creation |
| P-S6 | Quota protection | Dev runs use a small subset or few batches. Prod runs are rare | Proposed | Two environments share one Free Edition quota (risk R1) |

---

## 2. Classification handling by layer

Phase 1 decided what is classified ([03_governance_constraints.md](../01_discovery_scoping/03_governance_constraints.md) §2). This decides how each layer handles it.

| Layer | Restricted data handling | Enforcement |
|---|---|---|
| **Landing** | Raw files with all columns. Locked down: only the ingestion identity can write, and engineers can read | Volume grants (§4) |
| **Bronze** | Stored as landed, including card number and personal fields. Schema access limited to `data-engineers`. Columns tagged | Schema grants plus tags (P-S5) |
| **Silver** | Normalized. Card number dropped or tokenized (lesson 3, P-G5). Direct identifiers kept in `customers` because Type 2 needs them. Columns tagged `Restricted`. No consumer grants | Schema grants plus tags |
| **Gold** | No direct identifiers by default (D-S1). The customer-detail view masks them | Column masks at the consumer boundary (P-S1) |

### Gold masking plan (D-S1)

| Column | Mask for `data-consumers` | Unmasked for |
|---|---|---|
| first_name, last_name | `***` | `pii-readers` |
| email_address | Local part hidden, domain kept (`***@example.com`) | `pii-readers` |
| phone_number | `***` | `pii-readers` |
| address, postal_zip | `***` | `pii-readers` |
| gender | `***` | `pii-readers` |
| card number | **Not present in Gold** | Nobody |

- The masking mechanism (a column mask on a Gold table or a dynamic view that checks group membership) is chosen in the Gold phase. Support for masks on Free Edition and on materialized views is **(VERIFY)**. Either option enforces at the consumer boundary.
- Gold outputs 1 and 3 (sales by franchise and day, franchise-to-supplier) contain no personal data. Output 2 uses `customer_id` and coarse attributes (country, continent), with the detail view as the only exception.
- `customer_id` is Internal (lesson 3, P-G2), so the customer-sales output is not masked.

---

## 3. Unity Catalog ownership

Every securable object is owned by a **group**, and ownership is set at creation.

| Object | Owner | Why |
|---|---|---|
| Catalogs `bakehouse_dev`, `bakehouse_prod` | `platform-admins` | Account-level lifecycle control |
| Schemas `bronze`, `silver` | `data-engineers` | Engineering-owned internals |
| Schema `gold` | `data-engineers`, with consumer grants only | Engineering owns, consumers read |
| Schema `landing` and its volume | `ingestion-writers` | Least-privilege write path |

### Privilege matrix (target model)

| Group | Catalog | `landing` | `bronze` | `silver` | `gold` |
|---|---|---|---|---|---|
| `platform-admins` | Owner | Admin | Admin | Admin | Admin |
| `ingestion-writers` | `USE CATALOG` | Owner. Write volume | None | None | None |
| `data-engineers` | `USE CATALOG` | Read volume | Owner | Owner | Owner |
| `data-consumers` | `USE CATALOG` | None | None | None | `USE SCHEMA`, `SELECT` |
| `pii-readers` | `USE CATALOG` | None | None | None | `SELECT`, plus the unmasked view of the customer-detail columns |

### Free Edition position (D-S3, DEVIATION until verified)

| Item | Plan |
|---|---|
| Groups creatable? | ☐ Yes ☐ No (you check, §8) |
| If yes | Create the five groups and apply the matrix |
| If no | The model stays as the **target**. Your user is the **documented interim owner**, and an ownership transfer script is prepared for when groups exist |
| Ingestion identity | The lesson uses a service principal. On Free Edition the pipeline probably runs as your user (VERIFY). Treat `ingestion-writers` as the target |
| Pipeline-created tables | They are owned by the identity that runs the pipeline. Check at Bronze whether a bundle `run_as` setting is available. Otherwise, run a scripted `ALTER ... OWNER TO` after deployment and log it as a deviation |

---

## 4. Storage guardrails

| Rule | Standard | Check |
|---|---|---|
| Tables | Unity Catalog **managed** tables in catalog managed storage | Test S-T3 |
| Files (landing, exports) | UC volumes | Test S-T2 |
| `dbfs:/` and `/dbfs` | **Prohibited** for persistent data. Scratch use only | Test S-T2 |
| Path access in code | Always `/Volumes/{catalog}/{schema}/{volume}/...`. Never raw bucket URIs | Test S-T2 |

### Why DBFS is prohibited
Data on the DBFS root sits outside Unity Catalog governance: no lineage, no audit, no fine-grained access control, and it is tied to one workspace. Managed tables and volumes give the same convenience with full governance. Anything written to DBFS would also bypass the erasure procedure from lesson 3.

### Landing paths

| Item | Value |
|---|---|
| Volume | `bakehouse_<env>.landing.extracts` |
| Layout | `/Volumes/bakehouse_<env>/landing/extracts/<source>/<yyyy>/<mm>/<dd>/<source>_<yyyymmddHH>.csv` |
| `<source>` values | `transactions`, `customers`, `suppliers`, `franchises`, `franchise_time_zones` |

The file naming follows lesson 2 and the `_batch_ts` rule from [02_data_design_keys_time.md](02_data_design_keys_time.md).

---

## 5. Secure storage chain

The lesson's standard chain is below, with its status in this engagement.

| Object | Purpose | Standard creator | In the lab |
|---|---|---|---|
| Storage credential | Wraps the cloud identity that can reach a bucket | Metastore admin | **N/A (DEVIATION).** No own bucket on Free Edition (VERIFY) |
| External location | Binds a storage path to a credential | Metastore admin | **N/A (DEVIATION)** |
| Volume | File access inside a schema, governed like a table | Schema owner | **Managed volume** in catalog storage (P-S3) |
| Managed location | Catalog or schema default for managed tables | Catalog owner | Default catalog storage. A catalog-level location only if Free Edition allows (VERIFY) |

For production, the handover would add the credential and external location, and the volume would become external. Nothing in the code changes, because code only uses `/Volumes/...` paths. This is the reason for the path rule.

---

## 6. Code structure (D-S4)

Planned layout. **Nothing below exists yet.** Documentation stays in the numbered phase folders, and code goes in one bundle folder.

```
lakehouse_build/
├── 01_discovery_scoping/      docs: Phase 1
├── 02_foundation_kickoff/     docs: Phase 2
├── 03_… to 06_…               docs: later phases, added as we reach them
└── bundle/                    all deployable code
    ├── databricks.yml         bundle config, with dev and prod targets
    ├── resources/             pipeline, job and warehouse definitions
    ├── src/
    │   ├── common/            shared conventions (keys, time, column names)
    │   ├── bronze/
    │   ├── silver/
    │   └── gold/
    ├── tests/                 validation checks (K-T, H-T, G-T, S-T tests)
    └── scripts/               export of samples, seed file, ownership transfer
```

| Item | Decision |
|---|---|
| Targets | `dev` maps to `bakehouse_dev`, `prod` maps to `bakehouse_prod`, with the catalog as a bundle variable |
| Code never hardcodes | catalog names, Volume paths or group names |
| Phase to folder mapping | Documented in the README when the bundle is created |
| Free Edition checks (VERIFY) | The Databricks CLI authenticates, `bundle validate` and `bundle deploy` work for serverless pipelines and jobs |

> [!NOTE]
> The lesson says the choice must be documented in the **foundation readiness record** and that the build sticks to it. When Phase 2 is complete, I'll assemble that record from lessons 1 to 3, as I did for the scoping document.

---

## 7. Impact on other documents

| Document | Change |
|---|---|
| Scoping document | CL-3: environments and table-budget counting. CL-4: masking enforced at Gold, tags in Bronze and Silver |
| [03_governance_constraints.md](../01_discovery_scoping/03_governance_constraints.md) | Test G-T1 refined. Approvals A10 to A13 added |
| Lesson 1 scope | "Dev/prod separation by catalog or schema (TBC)" is now resolved: separate catalogs |

### Risks
| # | Risk | Mitigation |
|---|---|---|
| R1 | Quota shared by dev and prod runs | P-S6 |
| R6 | Free Edition may not allow groups, a catalog per environment, masks, or CLI deployment | Checks in §8 before Bronze. Each has a documented fallback |

---

## 8. Checks for your workspace (fill in)

| # | Check | Result |
|---|---|---|
| 1 | Can you create groups? | ☐ Yes ☐ No |
| 2 | Can you create a catalog (`bakehouse_dev`)? | ☐ Yes ☐ No |
| 3 | Can you create a managed volume in it? | ☐ Yes ☐ No |
| 4 | Are column masks supported (and on materialized views)? | ☐ Yes ☐ No |
| 5 | Does the Databricks CLI authenticate, and does `bundle validate` run? | ☐ Yes ☐ No |
| 6 | Is `dbfs:/` root accessible for writing? (Should still be avoided) | ☐ Yes ☐ No |
| 7 | Can a pipeline run as a service principal, or only as your user? | ☐ SP ☐ User only |

## 9. Acceptance tests (feed the definition of done)

| # | Test | Phase |
|---|---|---|
| S-T1 | Every catalog, schema, volume and table has an owner that is a group, or is on the documented interim-owner list (query `information_schema`) | Each phase |
| S-T2 | The repo has no `dbfs:/`, `/dbfs` or raw bucket URI, and all file paths start with `/Volumes/` | Each phase, CI check |
| S-T3 | Every table is `MANAGED` with no custom location | Each phase |
| S-T4 | All Restricted columns in Bronze and Silver carry the `Restricted` tag | Bronze, Silver |
| S-T5 | `data-consumers` see masked values and `pii-readers` see unmasked ones. No direct identifier exists in Gold outside the detail view | Gold |
| S-T6 | Only `ingestion-writers` can write the landing volume. `data-engineers` can read it | Bronze |
| S-T7 | `bundle validate` passes for both targets, with no hardcoded catalog names | Each phase |

## 10. Open items

- [ ] **You:** fill in the checks in §8 and send me the results.
- [ ] Choose the masking mechanism in the Gold phase, based on check 4.
- [ ] Create the groups and catalogs after the checks, only when you say so.
- [ ] Customer approval of A10 to A13 in the approvals log.

## References
- [Unity Catalog overview](https://docs.databricks.com/aws/en/data-governance/unity-catalog/)
