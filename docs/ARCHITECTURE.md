# Architecture

Renders on GitHub and in most Markdown viewers (Mermaid). Keep diagrams updated when the contract changes.

## 1. Components

```mermaid
flowchart LR
  subgraph CENTRAL["Central control plane (Docker Compose)"]
    UI["React dashboard<br/>(REST + SSE)"] --> PX["Reverse proxy"]
    PX --> API["FastAPI API<br/>auth, sites, incidents,<br/>remediation manager"]
    API <--> PG[("PostgreSQL<br/>+ pgvector (P1)")]
    WK["Worker<br/>incident jobs, LangGraph agent"] <--> PG
    WK -. "LLM provider<br/>(redacted context)" .-> LLM(("LLM"))
  end
  subgraph SITE["Edge site (independent K3s)"]
    PR["Prometheus +<br/>exporters"] --> DET["Detector<br/>IF + baselines + forecast"]
    DET --> PROC["Event processor<br/>correlate, incidents"]
    PROC --> DB[("SQLite<br/>incidents + outbox")]
    DB --> CON["Site connector"]
    CON --> POL["Policy engine"]
    POL --> EXE["Executor<br/>ACT-001/002"]
    DB --> LC["Local console<br/>(read-only)"]
  end
  CON == "outbound mTLS only<br/>(batches + long-poll)" ==> PX
```

Direction rule: every arrow between sites and central is **initiated by the site**. Central never dials in.

## 2. Incident-to-recovery sequence

```mermaid
sequenceDiagram
  autonumber
  participant D as Detector (site)
  participant P as Processor (site)
  participant C as Connector (site)
  participant A as API/Worker (central)
  participant G as Agent (LangGraph)
  participant R as Remediation Manager
  participant L as Policy+Executor (site)
  D->>P: node.anomaly.detected
  P->>P: correlate + incident + outbox (one SQLite tx)
  C->>A: POST events/incidents batch (mTLS)
  A-->>C: per-item acks
  A->>G: start investigation
  loop bounded (<= 12 tool calls)
    G->>A: typed read-only tool call
    A-->>C: command (long-poll response)
    C->>C: run diagnostic (observer SA)
    C->>A: bounded result
    A-->>G: evidence
  end
  G->>R: proposal (action_id + typed params)
  R->>R: validate level, target UID, policy, expiry
  alt L2
    R->>R: wait approval (approver != requester)
  end
  R-->>C: remediation command
  C->>L: local policy re-check
  L->>L: execute (idempotent)
  L->>L: verify (15 s checks, >= 2 min healthy)
  C->>A: result + verification
  A->>A: incident -> RESOLVED / ESCALATED, SSE notify
```

## 3. Offline autonomy (Scenario B)

```mermaid
stateDiagram-v2
  [*] --> Connected
  Connected --> Disconnected: heartbeat/poll failures
  Disconnected --> Disconnected: detect, create incident, outbox grows
  Disconnected --> Disconnected: L1 action only if cached policy valid
  Disconnected --> Reconnecting: link restored
  Reconnecting --> Syncing: mTLS re-auth ok
  Syncing --> Connected: outbox drained, idempotent acks
  Disconnected --> Observing_only: policy expired or clock drift
  Observing_only --> Disconnected: fresh policy fetched
```

In `Observing_only`, detection and incident persistence continue; automatic remediation is disabled (fail closed). L2 operations wait; connectivity loss never upgrades L2 to L1.

## 4. Trust boundaries

```mermaid
flowchart TB
  U["Operator browser"] -- "HTTPS + session cookie + CSRF" --> API
  S["Site connector"] -- "mTLS, cert -> exactly one site" --> API
  API["Central API"] -- "tenant_id on every row" --> PG[("PostgreSQL")]
  API -- "validated typed commands only" --> S
  LLM["LLM (no credentials, no shell)"] -. "proposes IDs + params" .-> API
  S -- "observer SA: read-only" --> K8S["K3s API"]
  S -- "executor SA: allowlisted patch only" --> K8S
```

## 5. Repository map

| Path | Content |
|---|---|
| `src/aiops/contracts` | Pydantic models mirroring `contracts/schemas` |
| `src/aiops/common` | shared utilities (time, ids, redaction, logging) |
| `src/aiops/central/{api,worker,agent,remediation,db}` | central code |
| `src/aiops/edge/{detector,processor,connector,policy,executor,console_api}` | edge code |
| `web/` | React dashboard and local console page |
| `deploy/` | Compose, Helm `edge-stack`, QEMU lab |
| `experiments/` | fault library, harness, analysis, run metadata |
| `contracts/` | JSON schemas, examples, action catalogue, sample policy, autonomy matrix |
| `prompts/` | agent prompts and injection test payloads |
| `tests/` | unit, integration, security, e2e |
