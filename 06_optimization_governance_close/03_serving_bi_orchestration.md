# Serving, BI Integration and Orchestration – Bakehouse Lakehouse

| | |
|---|---|
| **Platform** | Databricks SQL Warehouses, Lakeflow Jobs, DABs |
| **Warehouse ID** | `3c88b7bfb51daab1` (Serverless Starter Warehouse) |
| **Phase** | Phase 6 – Optimization, Governance & Close |
| **Status** | COMPLETE |
| **Author** | Antigravity (BI & Infrastructure Architect) |
| **Traceability** | Aligns with [scoping_document.md](../01_discovery_scoping/scoping_document.md) §1, [01_architecture_compute_planning.md](../02_foundation_kickoff/01_architecture_compute_planning.md) |

---

## 1. SQL Warehouse Sizing and SKUs

Databricks SQL Warehouses provide the query engine for BI dashboards, ad-hoc analytics, and scheduled reporting. Sizing and SKU selection balance latency against DBU consumption.

```mermaid
flowchart LR
    subgraph WAREHOUSE_SKU["SQL Warehouse SKUs"]
        SLS["Serverless (Default)<br/>Instant Start, Photon, Predictive I/O"]
        PRO["Pro SKU<br/>Customer VPC Compute, Photon"]
        CLS["Classic SKU<br/>Entry-Level, Slower Start"]
    end

    subgraph WORKLOADS["Target Workloads"]
        BI["BI Dashboards (Power BI / Tableau)"]
        ADHOC["Ad-Hoc SQL Exploration"]
        BATCH["Scheduled Nightly Aggregations"]
    end

    SLS --> BI
    SLS --> ADHOC
    PRO -. Fallback if no Serverless .-> BI
    CLS -. Cost-Floor Batch .-> BATCH
```

### Sizing and SKU Strategy Matrix

| Dimension | Strategy & Guidance | Implemented Value on Bakehouse |
|---|---|---|
| **Selected SKU** | **Serverless** (Instant startup in seconds, Photon engine, Intelligent Workload Management) | `Serverless Starter Warehouse` |
| **Warehouse Sizing** | T-shirt sizes. Scale **UP** (e.g., 2X-Small $\rightarrow$ Small) for complex queries; scale **OUT** (more clusters) for concurrency | `2X-Small` (Sufficient for sub-50ms scans on Gold views) |
| **Auto-Stop Policy** | Aggressive idle shutdown to eliminate costs when analysts are inactive | **10 Minutes** auto-stop configured |
| **Scaling Policy** | Min clusters: 1, Max clusters: 1 (Dev) / 2 (Prod peak) | Autoscaling cluster count on queue pressure |

---

## 2. BI Integration on Unity Catalog Endpoints

BI applications (Power BI, Tableau, ThoughtSpot, Looker) connect directly to the Serverless SQL Warehouse via Unity Catalog endpoints. 

```mermaid
flowchart TD
    subgraph BI_CLIENTS["BI Consumer Applications"]
        PBI["Microsoft Power BI (DirectQuery)"]
        TAB["Tableau Server / Desktop"]
        SQL_CLI["DBeaver / JDBC / ODBC"]
    end

    subgraph ENDPOINT["Unity Catalog Governed Endpoint"]
        CONN["Serverless SQL Endpoint<br/>(dbc-654c8244-a596 / Port 443)"]
        AUTH["Service Principal / OAuth 2.0 Token"]
    end

    subgraph GOVERNED_VIEWS["Gold Consumer Boundary"]
        V_SALES["v_sales_daily"]
        V_CUST["v_customer_sales_summary<br/>(Dynamic PII Redaction)"]
        V_PERF["v_franchise_performance"]
    end

    BI_CLIENTS --> AUTH --> CONN --> GOVERNED_VIEWS
```

### Connection Configuration Parameters

| Parameter | Connection String Value | Verification / Best Practice |
|---|---|---|
| **Server Hostname** | `dbc-654c8244-a596.cloud.databricks.com` | Verified reachable over TLS 443 |
| **Port** | `443` | Standard HTTPS/TLS port |
| **Protocol / Transport** | HTTP / HTTPS | Direct Databricks Connector |
| **HTTP Path** | `/sql/1.0/warehouses/3c88b7bfb51daab1` | Points to dedicated Serverless Starter Warehouse |
| **Default Catalog** | `bakehouse_dev` (or `bakehouse_prod`) | Direct routing to target environment |
| **Default Schema** | `gold` | Exposes consumer views only (`v_*`) |
| **Authentication** | Service Principal OAuth M2M (Prod) / User OAuth (Dev) | Service principal eliminates personal user dependencies |

### Cloud Fetch Optimization
- **Mechanics:** When BI dashboards extract large datasets (e.g., annual transactions extract), Databricks **Cloud Fetch** bypasses the driver node and streams encrypted Arrow data chunks in parallel directly from cloud storage presigned URLs to the client.
- **Validation:** Drivers must support Cloud Fetch (ODBC/JDBC $\ge \text{v2.6.22}$). Egress firewall rules allow access to regional S3 presigned endpoints (`s3.us-east-2.amazonaws.com`).

---

## 3. Pipeline Orchestration with Lakeflow Jobs

The entire Medallion journey (Bronze $\rightarrow$ Silver $\rightarrow$ Gold ETL $\rightarrow$ Consumer Views $\rightarrow$ Quality Checks $\rightarrow$ Maintenance) is orchestrated as a single multi-task DAG in Lakeflow Jobs.

### Master Orchestration DAG Architecture

```mermaid
flowchart TD
    T1["refresh_medallion_pipeline<br/>(Serverless DLT Pipeline Task)"]
    T2["run_gold_views_ddl<br/>(SQL Task: gold_views.sql)"]
    T3["run_quality_checks<br/>(SQL Task: quality_checks.sql)"]
    T4["run_silver_maintenance<br/>(SQL Task: maintenance.sql)"]
    T5["run_bronze_maintenance<br/>(SQL Task: maintenance.sql)"]

    T1 -->|ALL_SUCCESS| T2
    T2 -->|ALL_SUCCESS| T3
    T3 -->|ALL_SUCCESS| T4
    T4 -->|ALL_SUCCESS| T5
```

### Master Job Settings (`bundle/resources/bakehouse_master_orchestration.job.yml`)
- **Job ID:** `250613608242315`
- **Name:** `[${bundle.target}] Bakehouse Master Lakehouse Orchestrator`
- **Sequential Free-Edition Guardrail:** Because Serverless compute capacity in the Free Edition permits 1 active serverless unit at a time, the pipeline runs first; upon pipeline completion, the warehouse executes the downstream SQL tasks sequentially.
- **Failure Halting:** Any task failure (`T1`, `T2`, or `T3`) immediately halts downstream execution, preventing corrupt views or unverified data from being exposed to consumers.
- **Schedule:** `0 0 6 * * ?` (Daily at 06:00 UTC, paused by default in dev).

---

## 4. CI/CD with Declarative Automation Bundles (DABs)

The entire infrastructure—pipelines, jobs, schemas, and queries—is defined as declarative code in `bundle/databricks.yml`.

### Deployment Lifecycle

| Action | Command | Outcome |
|---|---|---|
| **Syntax & Dependency Validation** | `databricks bundle validate --profile dev` | Validates YAML syntax, resource cross-references, and variables without making changes |
| **Continuous Integration Deployment** | `databricks bundle deploy --profile dev` | Deploys files to workspace `/Workspace/Users/.../.bundle/` and updates resources idempotently |
| **Ad-Hoc DAG Run** | `databricks bundle run bakehouse_master_orchestration --profile dev` | Executes the complete multi-task orchestrator |
| **Deterministic Rollback** | `git checkout <commit_hash> && databricks bundle deploy --profile dev` | Restores prior pipeline and job configurations in a single command |

### Pipeline as Cattle Principle
If all jobs, pipelines, and schema definitions in the Databricks workspace were deleted, the entire platform can be recreated cleanly and identically from scratch within minutes using:
```bash
git clone <repo_url>
cd lakehouse_build/bundle
databricks bundle deploy --target prod
```
