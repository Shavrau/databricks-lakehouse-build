# 01 · Architecture and Compute Planning

| | |
|---|---|
| **Phase** | 2 – Foundation & Kickoff |
| **Lesson** | Lecture – Architecture and Compute Planning |
| **Status** | DRAFT – the region fields in §2 are waiting for your workspace check |
| **Planning only** | No platform objects are created by this document |
| **Traces to** | [scoping_document.md](../01_discovery_scoping/scoping_document.md) §3 (periodicity, risk R1), §2 (SLAs), [02_workload_source_profiling.md](../01_discovery_scoping/02_workload_source_profiling.md) §4 (7.2x sizing basis) |

> **(VERIFY)** marks items to check against the real workspace or current cloud offerings. **(HYPOTHETICAL)** marks plans that can't be applied on Free Edition and exist to show the method.

---

## 1. Decisions in this lesson

Decisions **D-xx** (asked) were made by you. Decisions **P-xx** (proposed) are mine, with the rationale.

| ID | Decision | Choice | Source | Rationale |
|---|---|---|---|---|
| D-A1 | Open region and quota items from Phase 1 | You check the workspace and send the results. The fields in §2 are blank until then | Asked | Region alignment can't be signed off from memory |
| D-A2 | Node-family and autoscaling guidance | Include a clearly labelled **hypothetical customer-managed fallback plan** (§5) | Asked | Free Edition can't apply it. The plan shows the method and gives a handover plan if serverless is not allowed |
| D-A3 | How the "hourly" POS pipeline runs in the lab | **Event-driven.** One run processes every hourly batch that has arrived, started manually or on file arrival. The design stays hourly, and the 50% rule is measured per batch | Asked | Protects the Free Edition quota (risk R1) without changing the production design |
| P-A1 | Compute for everything | **Serverless** (notebooks, jobs, pipelines and SQL) | Proposed | Free Edition has no other option, and it is also the lesson's default for new builds, so no fallback is triggered |
| P-A2 | SQL warehouse | One serverless SQL warehouse for dashboards and ad-hoc queries (size and count VERIFY) | Proposed | Free Edition is expected to give one small warehouse. This limits what we can demonstrate for the 5 to 20 concurrent analysts (lesson 2) |
| P-A3 | One-off export | The export from `samples.bakehouse` to the Volume runs as a serverless notebook, and it is **not** part of the steady-state pipeline | Proposed | The pipeline reads only from the Volume. Steady state therefore has no dependency on where `samples` is hosted |
| P-A4 | Cloud for the hypothetical plan | **AWS** instance names, with Azure and GCP equivalents listed | Proposed | I believe Free Edition runs on AWS (VERIFY). The lesson table gives equivalents for all three clouds |
| P-A5 | Phase 1 volume profile | Treat it as **simulated**, not measured | Proposed | The lesson says Phase 1 measured events per hour and burst windows. Bakehouse is static, so we have an assumed profile (lesson 2) and not a measured one |

---

## 2. Region alignment

Everything must be in the **same cloud region**, because cross-region paths add egress cost and latency on every run.

### 2.1 Fill-in checklist (D-A1)

| Item | Value | Where to check |
|---|---|---|
| Cloud provider | ☐ | Workspace URL or account page |
| Workspace region | ☐ | Workspace account or admin settings |
| Landing storage (the UC Volume) region | ☐ | Same as the catalog's managed storage in Free Edition (VERIFY) |
| Catalog managed storage region | ☐ | Catalog details |
| Region match across the three | ☐ Yes ☐ No | |
| `samples` catalog visible and `samples.bakehouse` listed | ☐ Yes ☐ No | Catalog Explorer |
| Serverless compute daily quota | ☐ | Free Edition limits page or workspace notice |
| SQL warehouse available (name, size) | ☐ | SQL Warehouses page |

### 2.2 Service availability check (a scoping check, not an assumption)

| Capability needed | Required by | Available in this region? |
|---|---|---|
| Serverless notebook compute | Export notebook, development | ☐ |
| Serverless jobs | Scheduled and triggered runs | ☐ |
| Serverless pipelines (Lakeflow Spark Declarative Pipelines) | The medallion pipeline | ☐ |
| Serverless SQL warehouse | Dashboards, ad-hoc analysis | ☐ |
| Unity Catalog Volumes | Landing zone | ☐ |
| Column masks / row filters | Governance (lesson 3) | ☐ |
| AUTO CDC from snapshots | Customer Type 2 (lesson 4) | ☐ |
| GPU types | Not needed | N/A |

### 2.3 Co-location rules
- The pipeline reads **only** from the Volume. The `samples` catalog is touched only by the one-off export (P-A3).
- If the regions don't match, record it as a risk and record the actual egress impact. At this data volume the cost is negligible, but the check still counts because it proves the process.

---

## 3. Compute choice: Serverless first

| Workload | Compute | Reason |
|---|---|---|
| One-off export from `samples.bakehouse` | Serverless notebook | Short task, no management needed |
| Medallion pipeline (Bronze, Silver, Gold) | Serverless pipeline | Default in the lesson, and the only option |
| Scheduled and triggered runs | Serverless job | Event-driven in the lab (D-A3) |
| Dashboards and ad-hoc SQL | Serverless SQL warehouse | Scales by concurrency |
| Development and validation queries | Serverless notebook or SQL warehouse | Same as above |

**Triggers for customer-managed compute** (none apply today): custom libraries or init scripts, specific instance needs, serverless gaps in the chosen region. If one appears, the customer-managed fallback in §5 is the starting point.

### Lab run model (D-A3)

| Item | Production design | Lab behaviour |
|---|---|---|
| POS interval | 1 hour | 1 hour per batch (design unchanged) |
| Trigger | Hourly schedule | Manual, or on file arrival. One run drains all landed batches |
| 50% rule | Runtime ≤ 30 min per hourly run (target ≤ 15 min) | Measure the **per-batch** runtime and compare it against the same limits |
| Quota effect | 24 runs per day | A few runs per session, within the daily quota (VERIFY) |

---

## 4. Serverless reality check on the Phase 1 personas

| Persona | Concurrency (stated, +12 months) | What we can run in Free Edition |
|---|---|---|
| Operations dashboard | 1 refresh, more viewers | Feasible |
| Franchise analysts | 5 → 20 | Not demonstrable. Use a scripted multi-query test, then extrapolate using the warehouse concurrency settings |
| Data engineers | 2-3 → 5 | One user |
| Applications / APIs | Low → medium, bursty | Low only |

---

## 5. Customer-managed fallback plan (HYPOTHETICAL, D-A2)

> [!WARNING]
> This plan is **not implemented**. It shows how the lesson's method turns the Phase 1 profile into node and scaling choices. Instance specs and prices must be validated against current cloud offerings.

### 5.1 Node family and memory per core

The rule is to prefer fast networking and local SSDs, and to validate about **8 GB of memory per vCPU core** for general ETL.

| Candidate (AWS) | vCPU | Memory | GB per core | Local SSD | Meets 8 GB/core? |
|---|---|---|---|---|---|
| m5d.xlarge | 4 | 16 GB | 4 | Yes | **No** (VERIFY specs) |
| m5d.2xlarge | 8 | 32 GB | 4 | Yes | **No** |
| i3.xlarge | 4 | ~30.5 GB | ~7.6 | Yes | Close |
| r5d.xlarge | 4 | 32 GB | 8 | Yes | **Yes** |
| r5d.2xlarge | 8 | 64 GB | 8 | Yes | **Yes** |

**Finding:** the lesson's example table lists the `m5d` family for "4-8 vCPU / 32-64 GB (8GB/core)". By the specs above, `m5d` has only about 4 GB per core, so the ratio check fails for that family. A memory-optimized `r5d` fits the 8 GB per core target. This is why the lesson says to *validate* the ratio and not to trust family names. Some memory is also reserved for the runtime, so effective memory per core is lower.

Cloud equivalents (from the lesson): Azure `Standard_E*ds_v5` for memory-optimized, GCP `n2-highmem` + SSD (VERIFY).

### 5.2 Worker shape by workload

| Workload | Profile | Shape | Reason |
|---|---|---|---|
| POS hourly batch | General batch ETL | `r5d.xlarge` (4 vCPU / 32 GB) | Meets 8 GB/core |
| Dimension loads (customers, suppliers, franchises) | Small reference loads | Smallest viable single node | Cost floor matters more than throughput |
| Type 2 customer merge | Joins on a small table | Same as POS | Not shuffle heavy at this size |
| Gold aggregations | Wide joins | Move to 16 GB/core only if spill is observed | Don't pay for memory without evidence |

### 5.3 Autoscaling by profile

At lab volume (a few MB, about 15 MB at the 14x stress case) a **single node with no autoscaling** would be enough. The ranges below show the method for a production-sized profile. All numbers are placeholders to be confirmed in Phase 6 load testing.

| Profile signal (lesson 2) | Approach | Hypothetical setting |
|---|---|---|
| Steady hourly POS batches | Narrow range | 2-4 workers |
| 22:00 end-of-day burst | Wider range with a low floor | Floor 1-2, ceiling about 8 |
| Initial snapshot and backfill | Raise the ceiling for the backfill window, then restore | Temporary ceiling increase |
| Interactive analytics | SQL warehouse scaling by concurrency | Min 1, max 2-3 clusters |

SQL warehouse reasoning: a cluster handles roughly 10 concurrent queries (VERIFY). So 5 analysts need 1 cluster and 20 analysts need about 2, plus headroom for dashboard refreshes.

**Rule:** the floor covers the steady state and the ceiling covers the measured burst. In this build the burst is simulated, so the settings stay hypothetical.

---

## 6. Risks and impact on other documents

| # | Risk | Mitigation |
|---|---|---|
| R1 | Free Edition quota (existing) | Event-driven runs (D-A3). Record the actual quota in §2.1 |
| R4 | Region or service mismatch found late | Fill in §2.1 and §2.2 **before** Bronze work starts |
| R5 | Warehouse concurrency can't be demonstrated | Scripted multi-query test, plus a note in the runbook |

**Scoping document:** no contradiction. The decisions refine R1's mitigation and keep the 7.2x sizing basis. When §2.1 is filled in, the region VERIFY items in the scoping document can be closed.

---

## 7. Acceptance tests (feed the definition of done)

| # | Test | When |
|---|---|---|
| F-T1 | The workspace, Volume and catalog managed storage are in the same region (§2.1) | Before Bronze |
| F-T2 | Every service in §2.2 is confirmed available | Before Bronze |
| F-T3 | All pipelines, jobs and warehouses use serverless compute (check compute settings) | Each phase |
| F-T4 | Measured runtime per hourly batch is under 50% of the interval, with a target under 25% | From Bronze onward |
| F-T5 | Every candidate in §5.1 has its GB per core computed and compared with 8 | Documentation |

## 8. Open items

- [ ] **You:** fill in §2.1 and §2.2 from your workspace and send them to me.
- [ ] Validate the instance specs in §5.1 against current AWS offerings.
- [ ] Re-test the autoscaling ranges in §5.3 at Phase 6 load testing, on scaled replicas of the data.

## References
- [Serverless compute](https://docs.databricks.com/aws/en/compute/serverless/)
- [Unity Catalog overview](https://docs.databricks.com/aws/en/data-governance/unity-catalog/)
