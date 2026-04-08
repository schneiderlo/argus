# Architect Blueprint: Agent Workflow Orchestrator

This document is the self-contained **spec zero** for a lineage-aware software delivery orchestrator.

It is written so a future engineer or agent can begin implementation **without any prior chat context**.

The system must be able to:

1. start from zero,
2. discover what needs to be built,
3. produce implementation-ready specs,
4. plan the work without forgetting important areas,
5. execute implementation and verification through agents,
6. absorb new user requests during development,
7. replan safely without corrupting in-flight work,
8. preserve a full audit trail of decisions, attempts, and evidence.

The central design rule is:

> **Local execution problems are handled by retries and execution-stage transitions. Requirement changes are handled by versioned replanning.**

That distinction drives the architecture below.

---

## 1. System Architecture

```text
┌─────────────────────────────────────────────────────────────────────┐
│                          Browser (Svelte 5)                         │
│                                                                     │
│  ┌──────────────┐  ┌────────────────┐  ┌─────────────────────────┐  │
│  │ Task / DAG   │  │ Change Request │  │ Logs / Evidence /       │  │
│  │ View         │  │ Inspector      │  │ Human Input Inspector   │  │
│  └──────┬───────┘  └────────┬───────┘  └────────────┬────────────┘  │
│         └───────────────────┴───────────────────────┘               │
│                         WebSocket + REST                            │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ Tailscale / LAN
┌──────────────────────────────┴───────────────────────────────────────┐
│                        VM / Host (Rust Binary)                       │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                        Tokio Runtime                          │  │
│  │                                                                │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │  │
│  │  │ Scheduler    │  │ REST / WS    │  │ Event Broadcaster    │  │  │
│  │  │              │  │ Server       │  │                      │  │  │
│  │  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘  │  │
│  │         │                 │                     │              │  │
│  │  ┌──────┴─────────────────┴─────────────────────┴───────────┐  │  │
│  │  │                    Control Plane                          │  │  │
│  │  │  ┌───────────────┐ ┌───────────────┐ ┌─────────────────┐ │  │  │
│  │  │  │ Spec Version  │ │ Plan Version  │ │ Change Request  │ │  │  │
│  │  │  │ Manager       │ │ Manager       │ │ Manager         │ │  │  │
│  │  │  └──────┬────────┘ └──────┬────────┘ └────────┬────────┘ │  │  │
│  │  │         │                 │                   │          │  │  │
│  │  │  ┌──────┴─────────────────┴───────────────────┴───────┐  │  │  │
│  │  │  │ Traceability / Coverage / Supersession Engine      │  │  │  │
│  │  │  └──────┬──────────────────────────────────────────────┘  │  │  │
│  │  └─────────┼──────────────────────────────────────────────────┘  │  │
│  │            │                                                     │  │
│  │  ┌─────────┴──────────────────────────────────────────────────┐  │  │
│  │  │                    Execution Plane                         │  │  │
│  │  │  ┌──────────────┐ ┌──────────────┐ ┌────────────────────┐ │  │  │
│  │  │  │ Step Runner  │ │ Gate Engine  │ │ Workspace Manager  │ │  │  │
│  │  │  └──────┬───────┘ └──────┬───────┘ └──────────┬─────────┘ │  │  │
│  │  │         │                │                    │           │  │  │
│  │  │  ┌──────┴────────┐ ┌─────┴─────────┐ ┌────────┴────────┐  │  │  │
│  │  │  │ Agent         │ │ Deterministic │ │ Renderers       │  │  │  │
│  │  │  │ Executor      │ │ Command       │ │ (SPECS / PLAN)  │  │  │  │
│  │  │  │               │ │ Runner        │ │                 │  │  │  │
│  │  │  └───────────────┘ └───────────────┘ └─────────────────┘  │  │  │
│  │  └────────────────────────────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                      │                              │                │
│             ┌────────┴────────┐            ┌────────┴────────────┐   │
│             │ PostgreSQL      │            │ Git Repo + Worktrees │   │
│             │ (source of      │            │ /projects/{id}/repo  │   │
│             │ truth)          │            │ /workspaces/...      │   │
│             └─────────────────┘            └──────────────────────┘   │
└───────────────────────────────────────────────────────────────────────┘
```

---

## 2. Design Goals

### Primary goals

- Discover unknowns before implementation starts.
- Preserve completeness through explicit traceability and coverage ledgers.
- Support implementation planning as a dependency graph, not just a linear checklist.
- Allow multiple agent roles with auditable handoffs.
- Handle new user requests during development without losing control of scope.
- Prevent stale or superseded work from silently landing.
- Keep execution evidence deterministic and reviewable.

### Non-goals for v1

- Fully autonomous product strategy.
- Unlimited fully parallel repo mutation without workspace isolation.
- Free-form agent self-direction over task choice or lifecycle state.
- Using markdown files as the operational source of truth.
- Letting agent self-report alone decide pass/fail.

### Core principles

1. **Postgres owns operational truth.**
2. **Git/workspaces own content artifacts.**
3. **Specs and plans are versioned.**
4. **Tasks are logical work units; step runs are execution attempts.**
5. **Change requests trigger replanning, not ad hoc implementation spawning.**
6. **Deterministic evidence outranks agent opinion.**
7. **Future work must stay traceable to requirements and evidence.**
8. **Plans should be detailed just in time, not fully expanded too early.**

---

## 3. Core Concepts

| Concept | Definition |
|---|---|
| **Project** | A repo-backed software effort managed by the orchestrator. |
| **Workflow Run** | A long-lived orchestration lane for one development stream in a project. A project may have multiple workflow runs for mainline work, hotfixes, or experiments. |
| **Change Request** | A new user request, clarification, scope change, or hotfix that must be triaged into the correct change lane. |
| **Spec Version** | An immutable draft or approved version of the requirement/spec set. Each new approved version supersedes the previous approved one. |
| **Requirement Identity** | The stable logical identity of a requirement across spec versions. |
| **Requirement Snapshot** | The version-local rendering of a requirement inside one spec version. |
| **Coverage Item** | A checklist item for categories often forgotten, such as auth, migrations, observability, rollback, deployment, or privacy. |
| **Plan Version** | An immutable draft or approved task graph derived from one spec version. |
| **Task Identity** | The stable logical identity of a work unit across plan versions. |
| **Plan Task Snapshot** | The immutable version-local task node inside a plan version. Examples: `M1.2`, `API-Auth-01`, `DB-Migrate-02`. |
| **Task Instance** | The runtime work item for a task identity inside a workflow run. It owns live execution state and may legally continue across plan changes if adoption records a continuation decision. |
| **Continuation Decision** | The control-plane decision recorded during adoption that says a task instance should continue, reverify, salvage, supersede, defer, or cancel across a new plan/spec head. |
| **Step Run** | One execution attempt of a stage such as impact analysis, bundle authoring, implementation, verification, or integration. It binds a task instance to the exact snapshots it consumed. |
| **Workspace** | An isolated working copy or git worktree for a single execution attempt or integration run. |
| **Artifact** | A file or evidence object generated by a step run, such as `a3.md`, `handoff.md`, test output, or an executor-written structured sidecar. |
| **Trace Link** | A link joining requirement identity/snapshot → spec section → task identity/snapshot → verification check → evidence. |
| **Rendered View** | A markdown file such as `SPECS.md` or `IMPLEMENTATION_PLAN.md` generated from canonical DB state plus repo artifacts. |

---

## 4. Three Layers, Two Graphs

This is the single most important modeling decision.

### 4.1 Logical identity layer

Stable identities explain **what concept persists across replans**.

```text
Requirement Identity REQ-AUTH-07
Task Identity TASK-M1.2
```

These identities survive version changes.

### 4.2 Versioned snapshot graph (control plane)

The versioned snapshot graph describes **what is approved right now**.

```text
Spec Version S7
   ↓
Plan Version P4
   ├── Task Snapshot M1.1 -> Task Identity TASK-M1.1
   ├── Task Snapshot M1.2 -> Task Identity TASK-M1.2
   └── Task Snapshot M1.3 -> Task Identity TASK-M1.3
```

This graph changes only when a new plan version is drafted and approved.

### 4.3 Execution graph (runtime)

The execution graph describes **how a live work item is being executed**.

```text
Task Identity TASK-M1.3
   ↓
Task Instance TI-42
   ├── continuation via P4:M1.3
   ├── bundle_run_1
   ├── implement_run_1
   ├── verify_run_1
   ├── continuation via P5:M1.3b (decision = continue)
   └── verify_run_2
```

This graph changes constantly as retries, re-verifications, and integration runs occur.

### 4.4 Why the split matters

Without this split, the system cannot safely answer:

- whether a task was replaced by a new plan,
- whether an agent run failed or merely became stale,
- whether evidence maps to the current spec version,
- whether unaffected tasks may continue when scope changes,
- whether a task snapshot was replaced while the underlying runtime work item remained valid.

---

## 5. Source of Truth Rules

These rules are mandatory.

### 5.1 Postgres is canonical for operational state

Postgres is the source of truth for:

- current approved spec version,
- current approved plan version,
- change requests,
- requirement identities and requirement snapshots,
- task identities, plan task snapshots, and dependencies,
- task instance lifecycle state and continuation decisions,
- assumptions, decisions, risks, coverage items,
- execution attempts,
- freshness, impact invalidation, continuation, staleness, supersession,
- traceability links,
- human input requests,
- audit events.

### 5.2 Git/workspaces are canonical for repo artifacts

Git-backed workspaces are the source of truth for:

- spec markdown,
- `SPECS.md`,
- `IMPLEMENTATION_PLAN.md`,
- `.agents/{task_ref}/a3.md`,
- `.agents/{task_ref}/verification.md`,
- `.agents/{task_ref}/handoff*.md`,
- code changes,
- evidence files,
- review reports.

### 5.3 Rendered views are not operational truth

Agents must never parse a markdown table and treat it as canonical task state.

`SPECS.md` and `IMPLEMENTATION_PLAN.md` are generated views for humans and agents to read, not the source of scheduling or lifecycle truth.

### 5.4 Agents never choose tasks

The orchestrator assigns:

- exact `task_instance_id`,
- exact `plan_task_snapshot_id`,
- exact `task_ref`,
- exact `spec_version_id`,
- exact `plan_version_id`,
- exact `workspace_path`,
- exact allowed read paths,
- exact allowed write paths.

---

## 6. Lifecycle Overview

### 6.1 From zero to first implementation

```text
discover
  -> followup loop until critical unknowns are resolved
  -> spec patch/write
  -> spec review
  -> approve spec version S1
  -> plan patch/write
  -> plan review
  -> approve plan version P1
  -> render SPECS.md and IMPLEMENTATION_PLAN.md
  -> materialize next ready wave
  -> bundle
  -> implement
  -> verify
  -> integrate
```

### 6.2 New request during development

```text
new user request
  -> create change request CR-12
  -> impact analysis
  -> draft spec delta S8
  -> review spec delta
  -> approve S8
  -> draft plan delta P5
  -> review plan delta
  -> approve P5
  -> create continuation decisions for active task instances
  -> mark impacted task instances outdated or superseded
  -> bind unaffected task instances to carried-forward snapshots
  -> render updated views
  -> materialize next wave from P5
```

### 6.3 Local failure vs requirement change

- **Verification failure**: stay inside the execution graph and retry or block.
- **Requirement change**: go through change request → impact analysis → new versions.

Never confuse the two.

---

## 7. Change Request Model

A new request from the user is first-class and must not be smuggled into the normal execution DAG.

### 7.1 Change request kinds

- `clarification`
- `small_change`
- `cross_cutting`
- `defer_to_backlog`
- `hotfix`

### 7.2 Change lanes

Every change request is triaged into exactly one lane:

- `fast_path`: trivial or non-behavioral work that does not change logical requirements or task topology.
- `standard`: normal product or engineering scope change requiring impact analysis and versioned replanning.
- `emergency`: urgent incident or hotfix work that may start immediately, but must be reconciled back into the control plane before merge to the shared branch.

### 7.3 Change request states

```text
proposed
  -> triaged
  -> impact_assessed
  -> spec_drafted
  -> spec_approved
  -> plan_drafted
  -> plan_approved
  -> applied
  -> closed
```

Optional exit: `rejected`.

### 7.4 Required behavior

A change request must answer these questions before plan adoption:

- Which requirements change?
- Which spec files or sections change?
- Which task identities and plan task snapshots are impacted?
- Which running or planned work can continue untouched?
- Which task instances should continue, salvage, reverify, supersede, defer, or cancel?
- Is the request part of the current run or explicitly deferred?

Additional lane rules:

- `fast_path` may skip full spec/plan regeneration only when impact analysis proves no logical requirement or task graph change.
- `standard` must follow impact analysis -> spec -> plan -> adoption.
- `emergency` may create a bounded emergency task instance immediately, but post-hoc spec/plan reconciliation is mandatory before the change is considered integrated.

### 7.5 Impact analysis output

Impact analysis produces structured output, for example:

```json
{
  "change_request_key": "CR-12",
  "summary": "Add audit logging for all admin actions",
  "impacted_requirements": ["REQ-AUTH-07", "REQ-OBS-03"],
  "impacted_specs": ["specs/20-auth.md", "specs/30-observability.md"],
  "impacted_task_snapshots": ["P4:M1.3", "P4:M2.1"],
  "continuation_candidates": ["TASK-M1.2"],
  "superseded_tasks": ["TASK-M1.3"],
  "recommended_action": "replan_partial"
}
```

---

## 8. Version Lineage

Every important object must carry lineage.

### 8.1 Spec version lineage

A spec version stores:

- version number,
- parent spec version,
- change request that caused it,
- status (`draft`, `approved`, `superseded`, `rejected`),
- manifest hash or file manifest,
- approval metadata.

### 8.2 Plan version lineage

A plan version stores:

- version number,
- parent plan version,
- source spec version,
- status,
- task graph snapshot,
- approval metadata.

### 8.3 Requirement lineage

A requirement carries:

- stable requirement identity,
- one snapshot per spec version,
- change classification (`new`, `carried_forward`, `modified`, `removed`),
- source refs and acceptance criteria per snapshot.

### 8.4 Task lineage

A task carries:

- stable task identity,
- one snapshot per plan version,
- optional superseded snapshot,
- requirement coverage links per snapshot,
- shared surface metadata per snapshot,
- verification strategy and accepted evidence classes per snapshot.

### 8.5 Task-instance lineage

A task instance stores:

- workflow run,
- task identity,
- current bound task snapshot,
- current lifecycle state,
- continuation decisions across adopted plan versions,
- human-readable reason and next action for non-happy-path states.

### 8.6 Step-run lineage

A step run stores:

- step kind,
- task instance or scope label,
- task snapshot consumed,
- spec version consumed,
- plan version consumed,
- workspace used,
- input fingerprint,
- continuation decision consumed, if any,
- output artifacts,
- outcome.

This makes freshness and auditability possible.

---

## 9. Freshness, Staleness, and Supersession

These concepts must be first-class.

### 9.1 Validity check

Before a step run starts and before its completion is accepted, the orchestrator checks:

- the consumed spec and plan snapshots are either still current or have an approved continuation decision,
- the bound task instance is not `superseded`, `deferred`, or `cancelled`,
- the task instance has not been invalidated by impacted requirements, dependencies, or protected surfaces,
- the continuation decision for the current heads is one of `continue`, `reverify`, or `salvage`,
- the step run input fingerprint still matches any protected inputs declared by the task snapshot.

The orchestrator must not use global head equality alone as a validity rule.

### 9.2 Outcomes

If validity fails:

- if the run has not started and the task instance is impacted, mark the step run `stale` and do not launch it,
- if the run has not started and the task instance is unaffected, create or reuse a continuation decision and rebind it to the carried-forward snapshot,
- if the run is already executing and becomes impacted, allow it to finish in isolation and mark the result `salvage_candidate` until adoption records whether it is reusable,
- if the run is already executing and remains unaffected, accept completion against the continuation decision rather than the original head equality.

### 9.3 Task semantics

- **stale** = the step run no longer matches approved continuation rules and should not be used as current evidence.
- **salvage_candidate** = a completed run produced potentially useful output after an adoption change and awaits an explicit reuse decision.
- **superseded** = a new task explicitly replaces this task in a newer plan version.

These are not the same as **failed**.

---

## 10. Rolling-Wave Planning

The system must avoid over-expanding detailed task artifacts too early.

### 10.1 Rule

The plan version may contain the full logical task graph, but detailed bundle generation and execution should happen **just in time** for the next ready wave.

### 10.2 Why

If every future task gets a detailed bundle immediately, a mid-flight request invalidates too much work.

### 10.3 Policy

For v1:

- allow the full logical plan to exist in the control plane,
- only materialize bundle/implement/verify step runs for task instances whose dependencies are satisfied and whose inputs remain valid under the current continuation rules.

---

## 11. State Models

### 11.1 Task-instance lifecycle states

These belong to **task instances**, not plan task snapshots.

```text
queued -> planning -> ready -> doing -> awaiting_verification -> done
                           \-> blocked
                           \-> salvage_candidate
                           \-> outdated
                           \-> deferred
                           \-> superseded
```

Definitions:

- `queued`: task instance exists but is not yet ready for bundling or continuation.
- `planning`: bundle creation is in progress.
- `ready`: bundle exists and the task instance is ready for implementation when deps allow.
- `doing`: implementation or repair attempt is in progress.
- `awaiting_verification`: an implementation handoff exists and is awaiting independent verification.
- `done`: verification passed and required evidence exists.
- `blocked`: verification failed or a hard prerequisite is missing.
- `salvage_candidate`: a running attempt completed after adoption changed and needs an explicit reuse decision.
- `outdated`: the task instance is no longer valid for the current approved inputs.
- `superseded`: the underlying task identity was explicitly replaced by a newer task identity.
- `deferred`: task was intentionally moved out of the current active scope.

### 11.2 Step-run engine states

These belong to **execution attempts**.

```text
pending -> ready -> running -> evaluating -> completed
                           \-> waiting_input
                           \-> failed
                           \-> cancelled
                           \-> stale
```

### 11.3 Step outcomes

A step run may end with:

- `pass`
- `fail`
- `blocked`
- `needs_input`
- `stale`
- `salvage_candidate`
- `superseded`
- `cancelled`
- `replan_requested`

### 11.4 Change request states

```text
proposed -> triaged -> impact_assessed -> spec_drafted -> spec_approved
         -> plan_drafted -> plan_approved -> applied -> closed
```

### 11.5 Task status ownership

Only the orchestrator changes task-instance lifecycle state. Plan task snapshots are immutable.

Suggested mapping:

- bundle start → `planning`
- bundle pass → `ready`
- implement start → `doing`
- implement pass → `awaiting_verification`
- verify start → `awaiting_verification`
- verify pass → `done`
- deterministic verification fail → `blocked`
- plan adoption carrying task forward unchanged → continue current instance with a new continuation decision
- plan adoption invalidating an active run → `salvage_candidate` or `outdated`
- plan adoption replacing task identity → `superseded`

### 11.6 User-facing state projection

The UI should project the richer internal states into a simpler primary set:

- `queued`
- `in_progress`
- `awaiting_verification`
- `done`
- `blocked`
- `outdated`

Every non-happy-path state must include a human-readable reason and next action.

---

## 12. PostgreSQL Schema

The schema below is concrete enough to guide implementation. It is not intended to be the only valid physical schema, but any implementation must preserve the same semantics.

### 12.1 Enums

```sql
CREATE TYPE workflow_run_state AS ENUM ('active', 'paused', 'completed', 'failed', 'cancelled');
CREATE TYPE change_request_kind AS ENUM ('clarification', 'small_change', 'cross_cutting', 'defer_to_backlog', 'hotfix');
CREATE TYPE change_request_lane AS ENUM ('fast_path', 'standard', 'emergency');
CREATE TYPE change_request_state AS ENUM ('proposed', 'triaged', 'impact_assessed', 'spec_drafted', 'spec_approved', 'plan_drafted', 'plan_approved', 'applied', 'closed', 'rejected');
CREATE TYPE version_status AS ENUM ('draft', 'approved', 'superseded', 'rejected');
CREATE TYPE requirement_kind AS ENUM ('functional', 'non_functional', 'constraint');
CREATE TYPE requirement_disposition AS ENUM ('active', 'deferred', 'removed');
CREATE TYPE change_class AS ENUM ('new', 'carried_forward', 'modified', 'removed', 'supersedes');
CREATE TYPE coverage_status AS ENUM ('open', 'addressed', 'deferred', 'not_applicable');
CREATE TYPE task_instance_status AS ENUM ('queued', 'planning', 'ready', 'doing', 'awaiting_verification', 'done', 'blocked', 'salvage_candidate', 'outdated', 'superseded', 'deferred');
CREATE TYPE dependency_kind AS ENUM ('hard', 'soft', 'integration');
CREATE TYPE surface_kind AS ENUM ('module', 'file_glob', 'db_table', 'api', 'event', 'config', 'infra');
CREATE TYPE continuation_disposition AS ENUM ('continue', 'reverify', 'salvage', 'supersede', 'defer', 'cancel');
CREATE TYPE workspace_state AS ENUM ('open', 'sealed', 'merged', 'discarded', 'closed');
CREATE TYPE step_kind AS ENUM ('discover', 'followup', 'impact_analysis', 'spec_patch', 'spec_review', 'plan_patch', 'plan_review', 'bundle', 'implement', 'verify', 'integrate', 'reconcile', 'human_gate');
CREATE TYPE engine_state AS ENUM ('pending', 'ready', 'running', 'evaluating', 'completed', 'failed', 'waiting_input', 'cancelled', 'stale');
CREATE TYPE step_outcome AS ENUM ('pass', 'fail', 'blocked', 'needs_input', 'stale', 'salvage_candidate', 'superseded', 'cancelled', 'replan_requested');
CREATE TYPE evidence_class AS ENUM ('local_deterministic', 'environment_deterministic', 'observational', 'human_attestation');
CREATE TYPE check_status AS ENUM ('pass', 'fail', 'skipped');
```

### 12.2 Projects and workflow runs

```sql
CREATE TABLE projects (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name            TEXT NOT NULL,
  slug            TEXT NOT NULL UNIQUE,
  repo_path       TEXT NOT NULL,
  default_branch  TEXT NOT NULL DEFAULT 'main',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE workflow_runs (
  id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id              UUID NOT NULL REFERENCES projects(id),
  name                    TEXT NOT NULL,
  state                   workflow_run_state NOT NULL DEFAULT 'active',
  head_branch             TEXT NOT NULL DEFAULT 'main',
  current_spec_version_id UUID,
  current_plan_version_id UUID,
  created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at            TIMESTAMPTZ
);
```

### 12.3 Change requests

```sql
CREATE TABLE change_requests (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_run_id   UUID NOT NULL REFERENCES workflow_runs(id),
  cr_key            TEXT NOT NULL,
  kind              change_request_kind NOT NULL,
  lane              change_request_lane NOT NULL DEFAULT 'standard',
  state             change_request_state NOT NULL DEFAULT 'proposed',
  title             TEXT NOT NULL,
  description       TEXT NOT NULL,
  requested_by      TEXT,
  priority          SMALLINT NOT NULL DEFAULT 3 CHECK (priority BETWEEN 1 AND 5),
  source            TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('user', 'system', 'agent')),
  idempotency_key   TEXT,
  decision_summary  TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  triaged_at        TIMESTAMPTZ,
  closed_at         TIMESTAMPTZ,
  UNIQUE (workflow_run_id, cr_key),
  UNIQUE (workflow_run_id, idempotency_key)
);
```

### 12.4 Spec control plane

```sql
CREATE TABLE spec_versions (
  id                             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_run_id                UUID NOT NULL REFERENCES workflow_runs(id),
  version_no                     INTEGER NOT NULL,
  parent_spec_version_id         UUID REFERENCES spec_versions(id),
  status                         version_status NOT NULL DEFAULT 'draft',
  title                          TEXT NOT NULL,
  summary                        TEXT,
  derived_from_change_request_id UUID REFERENCES change_requests(id),
  manifest_sha256                TEXT,
  created_at                     TIMESTAMPTZ NOT NULL DEFAULT now(),
  approved_at                    TIMESTAMPTZ,
  superseded_at                  TIMESTAMPTZ,
  UNIQUE (workflow_run_id, version_no)
);

CREATE TABLE requirement_defs (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_run_id    UUID NOT NULL REFERENCES workflow_runs(id),
  requirement_key    TEXT NOT NULL,
  kind               requirement_kind NOT NULL,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (workflow_run_id, requirement_key)
);

CREATE TABLE requirement_snapshots (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  requirement_def_id UUID NOT NULL REFERENCES requirement_defs(id),
  spec_version_id    UUID NOT NULL REFERENCES spec_versions(id),
  disposition        requirement_disposition NOT NULL DEFAULT 'active',
  title              TEXT NOT NULL,
  statement          TEXT NOT NULL,
  change_kind        change_class NOT NULL DEFAULT 'new',
  acceptance_criteria JSONB NOT NULL DEFAULT '[]'::jsonb,
  verification_notes TEXT,
  source_refs        JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (spec_version_id, requirement_def_id)
);

CREATE TABLE assumptions (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  spec_version_id  UUID NOT NULL REFERENCES spec_versions(id),
  assumption_key   TEXT NOT NULL,
  statement        TEXT NOT NULL,
  source           TEXT NOT NULL,
  status           TEXT NOT NULL CHECK (status IN ('pending', 'accepted', 'rejected')),
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (spec_version_id, assumption_key)
);

CREATE TABLE decisions (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  spec_version_id  UUID NOT NULL REFERENCES spec_versions(id),
  adr_key          TEXT NOT NULL,
  title            TEXT NOT NULL,
  status           TEXT NOT NULL CHECK (status IN ('proposed', 'accepted', 'deprecated', 'rejected')),
  context          TEXT NOT NULL,
  decision         TEXT NOT NULL,
  consequences     TEXT NOT NULL,
  alternatives     JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (spec_version_id, adr_key)
);

CREATE TABLE risks (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  spec_version_id  UUID NOT NULL REFERENCES spec_versions(id),
  risk_key         TEXT NOT NULL,
  title            TEXT NOT NULL,
  likelihood       SMALLINT NOT NULL CHECK (likelihood BETWEEN 1 AND 5),
  impact           SMALLINT NOT NULL CHECK (impact BETWEEN 1 AND 5),
  mitigation       TEXT NOT NULL,
  validation_plan  TEXT NOT NULL,
  status           TEXT NOT NULL CHECK (status IN ('open', 'accepted', 'mitigated', 'retired')),
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (spec_version_id, risk_key)
);

CREATE TABLE coverage_items (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  spec_version_id  UUID NOT NULL REFERENCES spec_versions(id),
  category         TEXT NOT NULL,
  item_key         TEXT NOT NULL,
  prompt           TEXT NOT NULL,
  status           coverage_status NOT NULL DEFAULT 'open',
  rationale        TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (spec_version_id, item_key)
);

CREATE TABLE spec_artifacts (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  spec_version_id  UUID NOT NULL REFERENCES spec_versions(id),
  path             TEXT NOT NULL,
  sha256           TEXT,
  purpose          TEXT,
  UNIQUE (spec_version_id, path)
);
```

### 12.5 Plan control plane

```sql
CREATE TABLE plan_versions (
  id                             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_run_id                UUID NOT NULL REFERENCES workflow_runs(id),
  spec_version_id                UUID NOT NULL REFERENCES spec_versions(id),
  version_no                     INTEGER NOT NULL,
  parent_plan_version_id         UUID REFERENCES plan_versions(id),
  status                         version_status NOT NULL DEFAULT 'draft',
  title                          TEXT NOT NULL,
  summary                        TEXT,
  derived_from_change_request_id UUID REFERENCES change_requests(id),
  manifest_sha256                TEXT,
  created_at                     TIMESTAMPTZ NOT NULL DEFAULT now(),
  approved_at                    TIMESTAMPTZ,
  superseded_at                  TIMESTAMPTZ,
  UNIQUE (workflow_run_id, version_no)
);

CREATE TABLE task_defs (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_run_id    UUID NOT NULL REFERENCES workflow_runs(id),
  task_key           TEXT NOT NULL,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (workflow_run_id, task_key)
);

CREATE TABLE plan_task_snapshots (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  plan_version_id       UUID NOT NULL REFERENCES plan_versions(id),
  task_def_id           UUID NOT NULL REFERENCES task_defs(id),
  milestone             TEXT,
  title                 TEXT NOT NULL,
  summary               TEXT,
  parallel_lane         TEXT,
  shared_surface_notes  TEXT,
  verification_strategy JSONB NOT NULL DEFAULT '{}'::jsonb,
  accepted_evidence     evidence_class[] NOT NULL DEFAULT ARRAY['local_deterministic']::evidence_class[],
  readiness_rules       JSONB NOT NULL DEFAULT '[]'::jsonb,
  deliverables          JSONB NOT NULL DEFAULT '[]'::jsonb,
  supersedes_snapshot_id UUID REFERENCES plan_task_snapshots(id),
  change_kind           change_class NOT NULL DEFAULT 'new',
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (plan_version_id, task_def_id)
);

CREATE TABLE plan_task_dependencies (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  plan_version_id    UUID NOT NULL REFERENCES plan_versions(id),
  from_plan_task_snapshot_id  UUID NOT NULL REFERENCES plan_task_snapshots(id),
  to_plan_task_snapshot_id    UUID NOT NULL REFERENCES plan_task_snapshots(id),
  kind               dependency_kind NOT NULL DEFAULT 'hard',
  UNIQUE (plan_version_id, from_plan_task_snapshot_id, to_plan_task_snapshot_id)
);

CREATE TABLE plan_task_requirement_links (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  plan_task_snapshot_id  UUID NOT NULL REFERENCES plan_task_snapshots(id),
  requirement_snapshot_id UUID NOT NULL REFERENCES requirement_snapshots(id),
  coverage_kind    TEXT NOT NULL CHECK (coverage_kind IN ('implements', 'tests', 'documents', 'mitigates')),
  UNIQUE (plan_task_snapshot_id, requirement_snapshot_id, coverage_kind)
);

CREATE TABLE plan_task_surfaces (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  plan_task_snapshot_id UUID NOT NULL REFERENCES plan_task_snapshots(id),
  surface_kind     surface_kind NOT NULL,
  surface_ref      TEXT NOT NULL,
  conflict_policy  TEXT NOT NULL CHECK (conflict_policy IN ('shared', 'exclusive')),
  UNIQUE (plan_task_snapshot_id, surface_kind, surface_ref)
);

CREATE TABLE plan_artifacts (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  plan_version_id  UUID NOT NULL REFERENCES plan_versions(id),
  path             TEXT NOT NULL,
  sha256           TEXT,
  purpose          TEXT,
  UNIQUE (plan_version_id, path)
);
```

### 12.6 Execution plane

```sql
CREATE TABLE task_instances (
  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_run_id              UUID NOT NULL REFERENCES workflow_runs(id),
  task_def_id                  UUID NOT NULL REFERENCES task_defs(id),
  current_plan_task_snapshot_id UUID NOT NULL REFERENCES plan_task_snapshots(id),
  status                       task_instance_status NOT NULL DEFAULT 'queued',
  state_reason                 TEXT,
  next_action                  TEXT,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at                   TIMESTAMPTZ,
  completed_at                 TIMESTAMPTZ,
  UNIQUE (workflow_run_id, task_def_id)
);

CREATE TABLE continuation_decisions (
  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_run_id              UUID NOT NULL REFERENCES workflow_runs(id),
  task_instance_id             UUID NOT NULL REFERENCES task_instances(id),
  from_plan_version_id         UUID REFERENCES plan_versions(id),
  to_plan_version_id           UUID NOT NULL REFERENCES plan_versions(id),
  previous_plan_task_snapshot_id UUID REFERENCES plan_task_snapshots(id),
  next_plan_task_snapshot_id   UUID REFERENCES plan_task_snapshots(id),
  disposition                  continuation_disposition NOT NULL,
  reason                       TEXT NOT NULL,
  impacted_surfaces            JSONB NOT NULL DEFAULT '[]'::jsonb,
  impacted_requirements        JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at                   TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (task_instance_id, to_plan_version_id)
);

CREATE TABLE workspaces (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_run_id   UUID NOT NULL REFERENCES workflow_runs(id),
  role              TEXT NOT NULL CHECK (role IN ('task', 'integration', 'analysis')),
  path              TEXT NOT NULL,
  base_branch       TEXT NOT NULL,
  base_commit       TEXT NOT NULL,
  head_ref          TEXT,
  state             workspace_state NOT NULL DEFAULT 'open',
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  sealed_at         TIMESTAMPTZ,
  merged_at         TIMESTAMPTZ,
  closed_at         TIMESTAMPTZ,
  UNIQUE (path)
);

CREATE TABLE step_runs (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_run_id    UUID NOT NULL REFERENCES workflow_runs(id),
  task_instance_id   UUID REFERENCES task_instances(id),
  plan_task_snapshot_id UUID REFERENCES plan_task_snapshots(id),
  change_request_id  UUID REFERENCES change_requests(id),
  scope_ref          TEXT NOT NULL,
  step_kind          step_kind NOT NULL,
  attempt_no         INTEGER NOT NULL DEFAULT 1,
  engine_state       engine_state NOT NULL DEFAULT 'pending',
  outcome            step_outcome,
  continuation_decision_id UUID REFERENCES continuation_decisions(id),
  spec_version_id    UUID REFERENCES spec_versions(id),
  plan_version_id    UUID REFERENCES plan_versions(id),
  workspace_id       UUID REFERENCES workspaces(id),
  input_fingerprint  TEXT,
  summary            TEXT,
  retry_count        INTEGER NOT NULL DEFAULT 0,
  max_retries        INTEGER NOT NULL DEFAULT 2,
  started_at         TIMESTAMPTZ,
  completed_at       TIMESTAMPTZ,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE step_edges (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_run_id    UUID NOT NULL REFERENCES workflow_runs(id),
  from_step_run_id   UUID NOT NULL REFERENCES step_runs(id),
  to_step_run_id     UUID NOT NULL REFERENCES step_runs(id),
  edge_label         TEXT,
  UNIQUE (from_step_run_id, to_step_run_id)
);

CREATE TABLE agent_sessions (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  step_run_id        UUID NOT NULL REFERENCES step_runs(id),
  agent_cli          TEXT NOT NULL,
  system_prompt      TEXT NOT NULL,
  user_message       TEXT,
  cwd                TEXT NOT NULL,
  context_paths      TEXT[] NOT NULL DEFAULT '{}',
  raw_stdout         TEXT,
  raw_stderr         TEXT,
  exit_code          INTEGER,
  tokens_in          INTEGER,
  tokens_out         INTEGER,
  cost_usd           NUMERIC(10, 6),
  duration_ms        INTEGER,
  started_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at       TIMESTAMPTZ
);

CREATE TABLE command_executions (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  step_run_id        UUID NOT NULL REFERENCES step_runs(id),
  phase              TEXT NOT NULL CHECK (phase IN ('author_sanity', 'verification', 'coverage', 'integration', 'gate')),
  command            TEXT NOT NULL,
  cwd                TEXT NOT NULL,
  exit_code          INTEGER,
  stdout_path        TEXT,
  stderr_path        TEXT,
  started_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at       TIMESTAMPTZ
);

CREATE TABLE verification_checks (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  step_run_id        UUID NOT NULL REFERENCES step_runs(id),
  requirement_snapshot_id UUID REFERENCES requirement_snapshots(id),
  check_name         TEXT NOT NULL,
  evidence_class     evidence_class NOT NULL,
  status             check_status NOT NULL,
  evidence_path      TEXT,
  details            TEXT
);

CREATE TABLE artifacts (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  step_run_id        UUID NOT NULL REFERENCES step_runs(id),
  workspace_id       UUID REFERENCES workspaces(id),
  path               TEXT NOT NULL,
  artifact_kind      TEXT NOT NULL,
  sha256             TEXT,
  metadata           JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (step_run_id, path)
);
```

### 12.7 Traceability, events, and human input

```sql
CREATE TABLE trace_links (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_run_id    UUID NOT NULL REFERENCES workflow_runs(id),
  source_kind        TEXT NOT NULL,
  source_id          UUID NOT NULL,
  target_kind        TEXT NOT NULL,
  target_id          UUID NOT NULL,
  relation           TEXT NOT NULL,
  UNIQUE (source_kind, source_id, target_kind, target_id, relation)
);

CREATE TABLE events (
  id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workflow_run_id    UUID NOT NULL REFERENCES workflow_runs(id),
  step_run_id        UUID REFERENCES step_runs(id),
  event_type         TEXT NOT NULL,
  payload            JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE human_input_requests (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_run_id    UUID NOT NULL REFERENCES workflow_runs(id),
  step_run_id        UUID NOT NULL REFERENCES step_runs(id),
  prompt             TEXT NOT NULL,
  schema             JSONB,
  response           JSONB,
  status             TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'answered', 'cancelled')),
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  answered_at        TIMESTAMPTZ
);
```

### 12.8 Useful views

```sql
CREATE VIEW requirement_traceability_gaps AS
SELECT rs.id, rd.requirement_key, rs.title
FROM requirement_snapshots rs
JOIN requirement_defs rd ON rd.id = rs.requirement_def_id
LEFT JOIN plan_task_requirement_links l ON l.requirement_snapshot_id = rs.id
WHERE rs.disposition = 'active'
GROUP BY rs.id, rd.requirement_key, rs.title
HAVING COUNT(l.id) = 0;

CREATE VIEW invalidated_candidate_step_runs AS
SELECT sr.id, sr.step_kind, sr.scope_ref
FROM step_runs sr
JOIN workflow_runs wr ON wr.id = sr.workflow_run_id
JOIN task_instances ti ON ti.id = sr.task_instance_id
LEFT JOIN continuation_decisions cd
  ON cd.task_instance_id = sr.task_instance_id
 AND cd.to_plan_version_id = wr.current_plan_version_id
WHERE sr.engine_state IN ('pending', 'ready', 'running')
  AND (
    ti.status IN ('outdated', 'superseded', 'deferred') OR
    (
      (
        sr.spec_version_id IS DISTINCT FROM wr.current_spec_version_id OR
        sr.plan_version_id IS DISTINCT FROM wr.current_plan_version_id
      )
      AND (
        cd.id IS NULL OR
        cd.disposition IN ('supersede', 'defer', 'cancel')
      )
    )
  );
```

---

## 13. Adoption Rules

Approving a version is a control-plane transaction, not an agent behavior.

### 13.1 Approving a spec version

Within one transaction:

1. mark the draft spec version `approved`,
2. mark the previous approved spec version `superseded`,
3. update `workflow_runs.current_spec_version_id`,
4. emit events:
   - `spec_version_approved`
   - `workflow_head_updated`

### 13.2 Approving a plan version

Within one transaction:

1. mark the draft plan version `approved`,
2. mark the previous approved plan version `superseded`,
3. update `workflow_runs.current_plan_version_id`,
4. create continuation decisions for active task instances,
5. update each task instance to continue, reverify, salvage, defer, supersede, or cancel,
6. emit events:
   - `plan_version_approved`
   - `workflow_head_updated`
   - `continuation_decided`
   - `task_outdated`
   - `task_superseded`

### 13.3 Reuse rules

When a new plan version is adopted:

- unaffected carried-forward task instances may remain active and bind to the new carried-forward snapshot,
- running impacted task instances become `salvage_candidate` until the continuation decision is resolved,
- tasks modified by the delta become `outdated` or `superseded`,
- already completed verified work is never silently rewritten; instead, new remediation or extension tasks are created if needed.

---

## 14. Completeness and Traceability Gates

This is how the system avoids forgetting important work.

### 14.1 Spec completeness gate

Before plan generation, the system must verify:

- fewer than the allowed number of unresolved critical discovery unknowns remain,
- all critical coverage items are not left `open`,
- each charter goal is represented by one or more requirements,
- high-impact risks have mitigation or explicit acceptance,
- major decisions are recorded and traceable.

### 14.2 Plan completeness gate

Before execution begins, the system must verify:

- every active requirement snapshot maps to at least one plan task snapshot,
- every plan task snapshot has a verification strategy and accepted evidence classes,
- behavior-changing tasks include runnable automated tests when local deterministic verification is the declared fit,
- migration, infrastructure, rollout, or operational tasks declare dry-run, rollback, staged, or observational checks as appropriate,
- deferred items are explicitly marked,
- dependency edges are explicit.

### 14.3 Verification completeness gate

Before a task is marked `done`, the system must verify:

- required commands ran,
- required checks passed,
- required evidence classes were satisfied,
- coverage gates passed where declared,
- evidence paths exist,
- verification reports were appended, not overwritten.

---

## 15. Agent Roles and Responsibilities

The system supports these role types.

| Step Kind | Responsibility |
|---|---|
| `discover` | Surface unknowns, assumptions, and questions before spec writing. |
| `followup` | Generate targeted follow-up questions after discovery or review. |
| `impact_analysis` | Assess which requirements, specs, tasks, and workspaces are impacted by a change request. |
| `spec_patch` | Create or update spec artifacts for foundation, domain, or delta work. |
| `spec_review` | Review specs for completeness, precision, and testability. |
| `plan_patch` | Produce or revise the logical task graph and execution plan. |
| `plan_review` | Review the plan for traceability, task sizing, dependency quality, and verification readiness. |
| `bundle` | Generate task-local A3 and verification bundles. |
| `implement` | Implement the assigned task in its isolated workspace and produce a handoff. |
| `verify` | Run the declared verification procedure and record AC-level results. |
| `integrate` | Merge or rehearse integration of verified work and run integration verification. |
| `reconcile` | Repair plan or control-plane mismatches discovered during integration or stale adoption. |
| `human_gate` | Wait for explicit human input or approval. |

### Mandatory rule

Agents do not:

- pick their own tasks,
- mutate task status directly,
- rewrite history,
- write outside the assigned workspace,
- commit to the shared integration branch directly.

---

## 16. File Layout

### 16.1 Human-readable persistent artifacts

```text
SPECS.md
IMPLEMENTATION_PLAN.md
specs/
  00-QUESTIONS.md
  00-ASSUMPTIONS.md
  00-CHARTER.md
  01-GLOSSARY.md
  02-DECISIONS.md
  03-RISKS.md
  10-*.md
  20-*.md
  _reviews/
.agents/{task_ref}/
  a3.md
  verification.md
  handoff-r{attempt_no}.md
  verification-report-r{attempt_no}.md
  technical-dive.md            # optional
  plan.md                      # optional
```

### 16.2 Machine-readable sidecars

These are always per-step-run so retries cannot trample each other. They are executor-owned canonical records, even when an agent emitted the underlying structured payload.

```text
.orchestrator/step-runs/{step_run_id}/
  result.json
  impact_analysis.json
  spec_delta.json
  plan_delta.json
  handoff.json
  verification_results.json
```

---

## 17. Agent Executor Protocol

### 17.1 Invocation flow

```text
Scheduler selects READY step run
        │
        ▼
1. PREPARE
   - allocate or reopen workspace
   - assemble prompt variables
   - prepare executor-owned sidecar target paths
   - select the agent adapter and output contract
   - transition step run to RUNNING
   - emit event: agent_invoked
        │
        ▼
2. SPAWN CLI PROCESS
   - cwd = assigned workspace
   - stdout/stderr captured
   - timeout enforced
   - heartbeat monitored
   - agent emits structured stdout and/or optional helper files
        │
        ▼
3. ON EXIT
   - save agent session
   - parse adapter output
   - capture artifacts and git diff
   - write canonical result envelope and typed sidecars
   - run deterministic gate commands if required
   - transition to EVALUATING
        │
        ▼
4. GATE EVALUATION
   - schema validation
   - file existence checks
   - command exit code checks
   - coverage checks
   - validity and continuation checks
   - task-instance state update by orchestrator
   - emit events
```

### 17.1a Agent adapter rule

Agents are not responsible for canonical filesystem bookkeeping. They may emit:

- structured stdout,
- structured stderr markers,
- optional helper files inside the assigned workspace.

The executor adapter is responsible for:

- normalizing agent output,
- writing `result.json` and typed sidecars,
- registering artifacts,
- attaching schema-validation errors to the step run rather than losing substantive work.

### 17.2 Workspace rules

For v1, each task attempt gets its own workspace or git worktree:

```text
/workspaces/{workflow_run_id}/{task_ref}/attempt-{n}
```

Metadata stored with the workspace:

- base branch,
- base commit,
- head ref,
- role (`task`, `integration`, `analysis`),
- status.

### 17.3 Heartbeat and timeout

Each running process is monitored for:

- liveness,
- timeout elapsed,
- recent filesystem activity,
- cancellation or staleness request.

Stale or cancelled runs are not allowed to merge automatically.

---

## 18. Deterministic Verification Policy

Deterministic evidence outranks agent self-report.

### 18.1 Evidence classes

Every task snapshot must declare one or more acceptable evidence classes:

- `local_deterministic`: local build, test, lint, schema, or file/hash checks.
- `environment_deterministic`: checks that require a real environment, ephemeral infra, or staged deployment target.
- `observational`: post-deploy telemetry, canary behavior, migration metrics, or monitored rollout evidence.
- `human_attestation`: explicit human approval for work that cannot be fully automated, always with an attached reason.

### 18.2 Allowed evidence sources

- command exit codes,
- structured check results,
- coverage outputs,
- build/test logs,
- file existence and hashes,
- schema validation,
- integration verification output,
- environment-specific checks,
- post-deploy observations,
- signed human attestations.

### 18.3 Role of verifier agents

Verifier agents are still valuable, but they are responsible for:

- executing the declared procedure,
- producing a readable report,
- linking results to requirements,
- highlighting root causes.

They are not the sole authority on pass/fail.

### 18.4 Minimum rules

- feature/bugfix/refactor tasks default to runnable automated tests unless another evidence class is explicitly justified,
- migration, infrastructure, and rollout-sensitive tasks must declare rollback and staged verification artifacts,
- observational evidence must include evaluation windows and success criteria,
- human attestation is allowed only when explicitly declared and must record approver, reason, and scope,
- coverage gates must be enforced exactly when declared,
- verification reports must never overwrite previous reports,
- negative and edge checks must be recorded where applicable.

---

## 19. Result Contracts

Every step run persists a generic `result.json` and may also persist a typed sidecar. The executor owns these canonical records.

### 19.1 Generic result contract

```json
{
  "status": "success",
  "sub_state": "DOING",
  "verdict": "Implementation handoff ready for independent verification",
  "files_read": ["SPECS.md", ".agents/M1.3/a3.md"],
  "files_written": ["src/auth/session.rs", ".agents/M1.3/handoff-r1.md"],
  "open_questions": [],
  "gate_hint": {
    "pass": true,
    "reason": "Required handoff and test evidence were produced"
  }
}
```

### 19.2 Typed sidecars

#### `impact_analysis.json`

```json
{
  "impacted_requirements": ["REQ-AUTH-07"],
  "impacted_specs": ["specs/20-auth.md"],
  "impacted_task_snapshots": ["P4:M1.3"],
  "continuation_candidates": ["TASK-M1.2"],
  "superseded_tasks": ["TASK-M1.3"],
  "recommended_action": "replan_partial"
}
```

#### `spec_delta.json`

```json
{
  "requirements_added": ["REQ-OBS-11"],
  "requirements_changed": ["REQ-AUTH-07"],
  "requirements_removed": [],
  "changed_files": ["specs/20-auth.md", "specs/30-observability.md"],
  "open_questions": []
}
```

#### `plan_delta.json`

```json
{
  "new_task_snapshots": ["P5:M1.3b"],
  "modified_task_snapshots": ["P5:M2.1"],
  "superseded_task_identities": ["TASK-M1.3"],
  "carried_forward_task_identities": ["TASK-M1.1", "TASK-M1.2"],
  "dependency_changes": [
    {"from": "P5:M1.2", "to": "P5:M1.3b", "kind": "hard"}
  ]
}
```

#### `handoff.json`

```json
{
  "task_ref": "M1.3b",
  "files_changed": ["src/auth/session.rs"],
  "commands_run": [
    {"cmd": "ctest -R auth_session", "exit_code": 0}
  ],
  "coverage": {
    "scope": "auth",
    "required_percent": 75,
    "actual_percent": 78.4
  },
  "known_risks": ["Fallback path not fully load-tested"]
}
```

#### `verification_results.json`

```json
{
  "task_ref": "M1.3b",
  "acceptance_checks": [
    {
      "requirement_key": "REQ-AUTH-07",
      "status": "pass",
      "evidence_path": ".agents/M1.3b/verification-report-r1.md"
    }
  ],
  "coverage_gate": {
    "required_percent": 75,
    "actual_percent": 78.4,
    "status": "pass"
  },
  "overall": "pass"
}
```

---

## 20. Workflow Template YAML

The YAML config is behavioral. It defines execution policy and prompt binding, but not the canonical state of tasks.

```yaml
name: "lineage-aware-agent-workflow"
version: 1
summary: >
  Software delivery orchestrator with versioned specs and plans,
  explicit change-request replanning, rolling-wave task materialization,
  isolated workspaces, and deterministic verification.

policies:
  source_of_truth:
    control_plane: "postgres"
    rendered_views:
      specs_index: "SPECS.md"
      implementation_plan: "IMPLEMENTATION_PLAN.md"
    repo_artifacts: "git_workspace"

  planning:
    mode: "rolling_wave"
    max_open_waves: 1
    bundle_generation: "just_in_time"
    render_views_after_version_adoption: true

  change_management:
    default_direct_spawn_from_user_request: false
    lanes:
      fast_path:
        allowed_when:
          - "no_requirement_identity_change"
          - "no_task_graph_change"
        required_flow:
          - "impact_analysis"
          - "approval"
      standard:
        required_flow:
          - "impact_analysis"
          - "spec_patch"
          - "spec_review"
          - "plan_patch"
          - "plan_review"
      emergency:
        immediate_execution_allowed: true
        posthoc_reconciliation_required: true
    allow_partial_reuse: true

  execution:
    workspace_strategy: "git_worktree_per_attempt"
    deterministic_verification_required: true
    agent_self_report_is_advisory: true
    freshness_checks:
      mode: "impact_scoped"
      before_dispatch: true
      before_accept_completion: true
      continuation_decision_required: true
      running_impacted_result: "salvage_candidate"
    conflict_surface_locking:
      enabled: true
      exclusive_surface_kinds: ["file_glob", "db_table", "api", "event", "infra"]

prompt_contract:
  shared_variables:
    - workflow_run_id
    - step_run_id
    - step_kind
    - change_request_id
    - spec_version_id
    - plan_version_id
    - task_instance_id
    - plan_task_snapshot_id
    - task_ref
    - workspace_path
    - required_read_paths
    - allowed_write_paths
    - output_contract
    - accepted_evidence_types
  forbidden_actions:
    - "select_a_different_task"
    - "mutate_task_state_directly"
    - "write_outside_workspace"
    - "rewrite_previous_verification_reports"
    - "commit_to_shared_branch"

schemas:
  result: "schemas/result.json"
  impact_analysis: "schemas/impact_analysis.json"
  spec_delta: "schemas/spec_delta.json"
  plan_delta: "schemas/plan_delta.json"
  handoff: "schemas/handoff.json"
  verification_results: "schemas/verification_results.json"

prompt_bindings:
  discover: "prompts/01-discovery-facilitator.md"
  followup: "prompts/02-follow-up-question-generator.md"
  impact_analysis: "prompts/02b-impact-analysis.md"
  spec_patch_foundation: "prompts/03-spec-writer.md"
  spec_review_foundation: "prompts/04-spec-verifier.md"
  spec_patch_phase: "prompts/05-domain-spec-writer.md"
  spec_review_phase: "prompts/06-domain-spec-verifier.md"
  plan_patch: "prompts/07-plan-generator.md"
  plan_review: "prompts/07b-plan-reviewer.md"
  bundle: "prompts/08-bundle-author.md"
  implement: "prompts/09-implementer.md"
  verify: "prompts/10-verifier.md"
  integrate: "prompts/10b-integrator.md"

step_kinds:
  discover:
    cli: "claude"
    timeout_sec: 900
    scope: "workflow_run"
    human_input: true
    gates:
      - type: "sidecar_schema"
        path: ".orchestrator/step-runs/{step_run_id}/result.json"
        schema: "schemas/result.json"

  followup:
    cli: "claude"
    timeout_sec: 600
    scope: "workflow_run"
    human_input: true
    gates:
      - type: "sidecar_schema"
        path: ".orchestrator/step-runs/{step_run_id}/result.json"
        schema: "schemas/result.json"

  impact_analysis:
    cli: "claude"
    timeout_sec: 600
    scope: "change_request"
    gates:
      - type: "sidecar_schema"
        path: ".orchestrator/step-runs/{step_run_id}/impact_analysis.json"
        schema: "schemas/impact_analysis.json"

  spec_patch:
    cli: "claude"
    timeout_sec: 900
    scope: "workflow_run_or_change_request"
    gates:
      - type: "files_exist"
        paths: ["SPECS.md", "specs/**"]
      - type: "sidecar_schema"
        path: ".orchestrator/step-runs/{step_run_id}/spec_delta.json"
        schema: "schemas/spec_delta.json"

  spec_review:
    cli: "codex"
    timeout_sec: 600
    scope: "workflow_run_or_change_request"
    human_input: true
    gates:
      - type: "report_exists"
        path: "specs/_reviews/**"

  plan_patch:
    cli: "claude"
    timeout_sec: 900
    scope: "workflow_run_or_change_request"
    human_input: true
    gates:
      - type: "sidecar_schema"
        path: ".orchestrator/step-runs/{step_run_id}/plan_delta.json"
        schema: "schemas/plan_delta.json"

  plan_review:
    cli: "codex"
    timeout_sec: 600
    scope: "workflow_run_or_change_request"
    human_input: true

  bundle:
    cli: "codex"
    timeout_sec: 600
    scope: "task_instance"
    task_state:
      on_start: "planning"
      on_pass: "ready"

  implement:
    cli: "codex"
    timeout_sec: 1800
    scope: "task_instance"
    task_state:
      on_start: "doing"
      on_pass: "awaiting_verification"
    required_artifacts:
      - ".agents/{task_ref}/a3.md"
      - ".agents/{task_ref}/verification.md"
      - ".agents/{task_ref}/handoff-r{attempt_no}.md"

  verify:
    cli: "codex"
    timeout_sec: 900
    scope: "task_instance"
    task_state:
      on_start: "awaiting_verification"
      on_pass: "done"
      on_fail: "blocked"
    gates:
      - type: "deterministic_verification"
      - type: "sidecar_schema"
        path: ".orchestrator/step-runs/{step_run_id}/verification_results.json"
        schema: "schemas/verification_results.json"

  integrate:
    cli: "codex"
    timeout_sec: 1200
    scope: "integration_wave"
    gates:
      - type: "integration_commands_pass"

automations:
  startup:
    - "render_specs_index"
    - "render_implementation_plan"

  on_plan_adopted:
    - "compute_continuation_decisions"
    - "mark_impacted_task_instances_outdated_or_superseded"
    - "render_implementation_plan"
    - "materialize_next_ready_wave"

  on_verify_fail:
    - "optionally_create_rework_attempt"

  on_change_request_created:
    - "create_impact_analysis_step"

  on_emergency_change_request_approved:
    - "create_bounded_emergency_task_instance"
```

---

## 21. Scheduler

The scheduler is the core loop. It runs inside the Tokio runtime.

### 21.1 Responsibilities

1. maintain current approved spec and plan heads,
2. compute impact invalidation and continuation decisions,
3. promote eligible step runs from `pending` to `ready`,
4. materialize just-in-time execution for next-wave task instances,
5. dispatch ready steps subject to concurrency and workspace rules,
6. collect process exits and deterministic evidence,
7. update task-instance state via orchestrator-owned mappings,
8. broadcast events,
9. detect completion or blockage.

### 21.2 Pseudocode

```rust
struct Scheduler;

impl Scheduler {
    async fn tick(&self) -> Result<()> {
        self.refresh_current_heads().await?;
        self.compute_invalidations_and_continuations().await?;
        self.materialize_next_ready_wave().await?;
        self.promote_pending_to_ready().await?;
        self.dispatch_ready_steps().await?;
        self.poll_running_processes().await?;
        self.process_completed_steps().await?;
        self.evaluate_workflow_completion().await?;
        Ok(())
    }
}
```

### 21.3 Materialization rules

A task instance is eligible for just-in-time execution materialization when:

- it is bound to a current or carried-forward plan task snapshot,
- its status is in the expected pre-materialization state,
- all hard dependencies of its bound task snapshot are done,
- it is not outdated, superseded, or deferred,
- any continuation decision for the current heads allows execution,
- no exclusive-surface conflict exists,
- no open blocking change request invalidates it.

### 21.4 Retry rules

Retries are allowed only for local execution failures and within a bounded policy.

Requirement changes do not trigger blind retries. They trigger replanning.

---

## 22. REST and WebSocket Protocol

### 22.1 REST examples

```text
POST   /projects
POST   /workflow-runs
GET    /workflow-runs/{id}
GET    /workflow-runs/{id}/tasks
GET    /workflow-runs/{id}/change-requests
POST   /workflow-runs/{id}/change-requests
POST   /human-input/{id}/respond
POST   /step-runs/{id}/retry
GET    /workflow-runs/{id}/artifacts
```

### 22.2 WebSocket events

Every stored event is also broadcast to subscribed clients.

Example:

```json
{
  "type": "event",
  "event": {
    "id": 12345,
    "workflow_run_id": "uuid",
    "step_run_id": "uuid",
    "event_type": "task_superseded",
    "payload": {
      "old_task_ref": "M1.3",
      "new_task_ref": "M1.3b",
      "plan_version_id": "uuid"
    },
    "created_at": "2026-03-18T16:42:00Z"
  }
}
```

Other useful event types:

- `state_change`
- `step_materialized`
- `agent_invoked`
- `agent_completed`
- `gate_evaluated`
- `change_request_created`
- `impact_analysis_completed`
- `spec_version_approved`
- `plan_version_approved`
- `continuation_decided`
- `task_outdated`
- `workflow_head_updated`
- `human_input_requested`
- `human_input_received`
- `artifact_written`
- `workspace_opened`
- `workspace_merged`
- `integration_failed`
- `workflow_completed`

---

## 23. Frontend Structure (Svelte 5)

```text
frontend/
├── src/
│   ├── lib/
│   │   ├── stores/
│   │   │   ├── workflow.svelte.ts
│   │   │   ├── change_requests.svelte.ts
│   │   │   ├── traceability.svelte.ts
│   │   │   └── websocket.svelte.ts
│   │   ├── components/
│   │   │   ├── DAGView.svelte
│   │   │   ├── TaskTable.svelte
│   │   │   ├── ChangeRequestInspector.svelte
│   │   │   ├── StepInspector.svelte
│   │   │   ├── EvidencePanel.svelte
│   │   │   ├── HumanInputForm.svelte
│   │   │   └── TraceabilityBoard.svelte
│   │   └── api/
│   │       └── client.ts
│   └── routes/
│       ├── +page.svelte
│       └── projects/[id]/runs/[runId]/+page.svelte
```

### Main views

- Task graph / table view
- Change request panel
- Step inspector and logs
- Traceability coverage board
- Human input queue
- Timeline / audit view

For v1, the default screen should be a timeline plus exception queue answering:

- what changed,
- what is blocked,
- what needs human input now.

A high-quality table view is more important than a fancy DAG renderer.

---

## 24. Backend Project Structure (Rust + Bazel + Nix)

Bazel remains the authoritative build and test entrypoint for the backend. Rust tooling metadata can be added if useful for editor support, but the orchestration system still treats Postgres, git workspaces, YAML, and rendered views exactly as defined elsewhere in this blueprint.

```text
orchestrator/
├── flake.nix
├── MODULE.bazel
├── BUILD.bazel
├── src/
│   ├── main.rs
│   ├── lib.rs
│   ├── config/
│   │   └── mod.rs
│   ├── db/
│   │   ├── mod.rs
│   │   ├── migrations/
│   │   ├── pool.rs
│   │   ├── models.rs
│   │   └── queries.rs
│   ├── control_plane/
│   │   ├── mod.rs
│   │   ├── spec_manager.rs
│   │   ├── plan_manager.rs
│   │   ├── requirement_manager.rs
│   │   ├── task_identity_manager.rs
│   │   ├── change_request_manager.rs
│   │   ├── traceability.rs
│   │   ├── coverage_ledger.rs
│   │   ├── continuation.rs
│   │   └── adoption.rs
│   ├── execution/
│   │   ├── mod.rs
│   │   ├── scheduler.rs
│   │   ├── task_instances.rs
│   │   ├── step_materializer.rs
│   │   ├── gate_evaluator.rs
│   │   ├── workspace_manager.rs
│   │   ├── executor.rs
│   │   ├── agent_adapter.rs
│   │   ├── process_monitor.rs
│   │   ├── result_parser.rs
│   │   ├── command_runner.rs
│   │   └── retention.rs
│   ├── render/
│   │   ├── mod.rs
│   │   ├── specs_renderer.rs
│   │   └── implementation_plan_renderer.rs
│   ├── events/
│   │   ├── mod.rs
│   │   ├── event_store.rs
│   │   └── event_types.rs
│   ├── web/
│   │   ├── mod.rs
│   │   ├── server.rs
│   │   ├── routes.rs
│   │   ├── ws_manager.rs
│   │   └── broadcaster.rs
│   └── workflow/
│       ├── mod.rs
│       ├── template_parser.rs
│       └── template_validator.rs
├── prompts/
│   ├── 01-discovery-facilitator.md
│   ├── 02-follow-up-question-generator.md
│   ├── 02b-impact-analysis.md
│   ├── 03-spec-writer.md
│   ├── 04-spec-verifier.md
│   ├── 05-domain-spec-writer.md
│   ├── 06-domain-spec-verifier.md
│   ├── 07-plan-generator.md
│   ├── 07b-plan-reviewer.md
│   ├── 08-bundle-author.md
│   ├── 09-implementer.md
│   ├── 10-verifier.md
│   └── 10b-integrator.md
├── schemas/
│   ├── result.json
│   ├── impact_analysis.json
│   ├── spec_delta.json
│   ├── plan_delta.json
│   ├── handoff.json
│   └── verification_results.json
└── tests/
    ├── control_plane/
    ├── execution/
    ├── render/
    └── workflow/
```

---

## 25. Example Scenario: Mid-Flight Change Request

The user says:

> Also add audit logging for all admin actions.

### Before the request

- current approved spec: `S7`
- current approved plan: `P4`
- `M1.1` done
- `M1.2` doing
- `M1.3` ready

### Correct behavior

1. create `CR-12`
2. run `impact_analysis`
3. output says:
   - impacted requirements: auth and observability
   - impacted task snapshots: `P4:M1.3`, `P4:M2.1`
   - continuation candidate: `TASK-M1.2`
   - superseded task identity: `TASK-M1.3`
4. draft spec version `S8`
5. review and approve `S8`
6. draft plan version `P5`
7. `P5` carries forward the task identity behind `M1.2`, supersedes the task identity behind `M1.3` with `M1.3b`, and adds `M2.1b`
8. adopt `P5`
9. create continuation decision `continue` for the running task instance behind `M1.2`
10. create continuation decision `supersede` for the queued task instance behind `M1.3`
11. mark `M1.3` as `superseded`
12. allow `M1.2` to continue because it is unaffected and now bound to the carried-forward snapshot in `P5`
13. if `M1.2` finishes after adoption, accept or reverify it against the continuation decision rather than rejecting it due to head mismatch
14. materialize bundle and implementation work for `M1.3b`
15. render updated `IMPLEMENTATION_PLAN.md`

This is the intended behavior. The system must not directly spawn an extra implementation task from the user request without spec and plan updates.

---

## 26. Critical Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---:|---:|---|
| Agent CLIs differ substantially in invocation model | High | High | Build an adapter interface per CLI and standardize prompt/result handling. |
| Executor/agent output contracts drift over time | High | High | Make adapters own canonical sidecars, validate contracts centrally, and version prompt/schema bindings. |
| Plan and task state drift from rendered markdown | High | High | Make markdown generated-only; never schedule from markdown. |
| Mid-flight change requests invalidate too much work | Medium | High | Use rolling-wave planning, continuation decisions, and impact-scoped invalidation instead of head equality. |
| Parallel tasks collide on the same repo surface | Medium | High | Use isolated workspaces and conflict-surface metadata. |
| Verification policy is too narrow for infra, migrations, or staged rollouts | High | High | Support multiple evidence classes and require rollback/staged verification artifacts when appropriate. |
| Retry loops grow unbounded | Medium | Medium | Bound retries and escalate to human or change-request flow. |
| Rust compile times and Bazel wiring can still lag behind config iteration | Medium | Medium | Keep behavior in YAML/prompts/schemas; keep Rust services small, modular, and strict. |
| Integration breaks after individually verified tasks pass | Medium | High | Make integration a first-class stage with dedicated checks. |
| Traceability becomes incomplete over time | Medium | High | Add explicit completeness views and adoption gates. |
| Execution exhaust grows without bound | Medium | Medium | Add retention, garbage collection, and object storage for large logs and artifacts. |

---

## 27. Build Sequence

The implementation order below is designed to minimize architecture risk.

| Phase | What | Depends On | Deliverable |
|---|---|---|---|
| **M0.1** | Minimal schema with logical identity, snapshot, runtime split | Nothing | Running DB with requirement/task identities, snapshots, task instances, and step runs |
| **M0.2** | One agent adapter + executor-owned result persistence | M0.1 | Canonical sidecars written by the system, not the agent |
| **M0.3** | One end-to-end task flow (`bundle -> implement -> verify`) | M0.1, M0.2 | Single-task vertical slice with deterministic evidence |
| **M1.1** | Spec version manager | M0.1 | Create, approve, supersede spec versions |
| **M1.2** | Plan version manager | M0.1, M1.1 | Create, approve, supersede plan versions |
| **M1.3** | Adoption + continuation decisions | M1.2 | Safe carry-forward, supersession, and salvage decisions |
| **M1.4** | Change request manager + impact storage | M0.1, M1.3 | First-class change request lifecycle and impact data |
| **M1.5** | One replan flow with carry-forward salvage | M1.1, M1.2, M1.3, M1.4 | `impact_analysis -> spec -> plan -> adoption` with unaffected work continuing |
| **M2.1** | Workspace manager | M0.3 | Per-attempt isolated workspaces |
| **M2.2** | Deterministic command runner + evidence classes | M0.3 | Persisted local and environment verification checks |
| **M2.3** | Scheduler core | M1.3, M2.1, M2.2 | Pending → ready promotion, continuation-aware dispatch, and run polling |
| **M2.4** | Integration step | M2.2, M2.3 | Verified merge/integration flow |
| **M3.1** | Renderers for `SPECS.md` and `IMPLEMENTATION_PLAN.md` | M1.1, M1.2 | Generated human-readable views from canonical state |
| **M3.2** | REST API | M2.3 | Create/query projects, runs, task instances, CRs |
| **M3.3** | WebSocket events + outbox delivery | M2.3, M3.2 | Real-time event push with durable emission |
| **M3.4** | Svelte app | M3.3 | Timeline, exception queue, task table, CR inspector |
| **M3.5** | Human input flow | M3.2, M3.3 | Review and approval pauses |
| **M4.1** | Traceability board + coverage ledger | M1.1, M1.2, M3.4 | Requirement coverage and completeness gates |
| **M4.2** | Multi-lane change policies + emergency reconciliation | M1.4, M2.3 | Fast path and emergency hotfix handling |
| **M4.3** | Retention, GC, RBAC, redaction, backups | M2.3 | Operational hardening |

### Bootstrap point

Do not attempt self-hosting or “system builds itself” until:

- change request flow exists,
- continuation and supersession are reliable,
- workspace isolation is implemented,
- deterministic verification is solid,
- traceability gaps are visible.

---

## 28. Final Rules for Future Implementers

Any implementation of this blueprint must preserve these invariants:

1. There is always exactly one current approved spec version per active workflow run.
2. There is always exactly one current approved plan version per active workflow run.
3. Requirement identities and task identities are stable across versions.
4. Spec versions and plan versions are immutable snapshots.
5. Task instances carry live runtime state; snapshots do not.
6. Step runs are execution attempts bound to explicit snapshots and, when needed, continuation decisions.
7. Standard changes do not directly spawn implementation work; emergency changes may do so only with mandatory post-hoc reconciliation.
8. Head changes alone do not invalidate work; invalidation must be impact-scoped.
9. Stale, salvage candidate, superseded, and failed are distinct.
10. Verification must be grounded in declared evidence classes, with deterministic evidence preferred by default.
11. Rendered markdown views are for reading, not scheduling truth.
12. Auditability is mandatory: every approval, attempt, command, artifact, continuation decision, and report must be reconstructible.

---

## 29. One-Sentence Summary

This orchestrator is a **versioned control plane plus a continuation-aware execution plane**: it keeps stable logical identities above immutable spec/plan snapshots, executes runtime task instances in isolated workspaces, verifies them with declared evidence classes, and absorbs new requests through impact-scoped replanning instead of invalidating good work by head change alone.



Design the workspace, execution, and integration subsystem for a lineage-aware “code factory” where 10
  to 50 AI agents run tasks concurrently against the same repository.

  ## Scope

  Design only the `workspace + execution + aggregation/integration` substrate, but design it so it fits
  cleanly inside a lineage-aware orchestrator with these invariants:

  - Postgres is the canonical source of operational truth.
  - Git/workspaces are the canonical source of repo artifacts.
  - Rendered views like `SPECS.md` and `IMPLEMENTATION_PLAN.md` are read-only views, never scheduling
  truth.
  - `spec_versions` and `plan_versions` are immutable snapshots.
  - Requirement identities and task identities are stable across versions.
  - `task_instances` carry live runtime state.
  - `step_runs` are per-attempt execution records bound to explicit inputs.
  - Mid-flight scope changes are handled by versioned replanning plus `continuation_decisions`, not ad
  hoc spawning.
  - Agents do not choose tasks and do not mutate orchestration state directly.
  - Deterministic evidence outranks agent self-report.

  Treat this as a subsystem inside that architecture, not as a standalone CI farm.

  ## Goal

  Produce a system design that enables many agents to work in parallel with:

  - near-instant warm workspace startup,
  - strong isolation,
  - shared dependency and build acceleration,
  - safe execution of untrusted task code on Linux,
  - efficient aggregation and staged integration of many concurrent outputs,
  - perfect provenance and reproducibility.

  ## Core problem

  Naive per-agent clones and per-agent dependency installs create catastrophic disk, CPU, and startup
  amplification.

  Examples of heavy shared state that must be handled explicitly:

  - Node.js: `node_modules`, pnpm store, yarn cache, npm cache, framework build caches
  - Python: virtualenvs, wheel caches, pip caches, uv caches
  - Rust: Cargo registry, git deps, `target/`
  - C/C++: compiler caches, object files, precompiled headers, Conan/vcpkg/homegrown trees
  - Bazel: repository cache, external fetches, action cache, disk cache, output base
  - CMake: configure trees, generated build files, toolchain discovery, out-of-source `build/` dirs

  The design must separate immutable shared artifacts from task-private writable state and must explain
  correctness boundaries for each ecosystem.

  ## Hard requirements

  ### Workspace and execution

  R1. Warm workspace provisioning target: `{{WORKSPACE_STARTUP_TARGET}}` (default: `< 1s`) from a
  prepared base. Model cold bootstrap separately and explicitly cost it.

  R2. Shared dependency caches and reusable build acceleration must be supported across tasks, but
  without cross-task contamination.

  R3. Strict isolation: Task A must not be able to read or modify Task B’s private writable workspace
  state. Shared immutable caches may be exposed read-only under orchestrator policy.

  R4. Perfect auditability: all VCS operations are server-owned and every accepted change is
  attributable to exact agent/session/task/step metadata.

  R5. Reproducibility: any task workspace and execution attempt must be reconstructible exactly from the
  audit trail and referenced base snapshots.

  R6. Safety: assume Linux hosts and that agent runtimes plus executed task code are untrusted.

  ### Blueprint alignment

  R7. Every workspace and execution attempt must bind to explicit `workflow_run`, `task_instance`,
  `plan_task_snapshot`, `spec_version`, `plan_version`, and `step_run` identifiers.

  R8. The design must explain how `continuation_decisions` work when a new spec/plan version is adopted
  mid-task, including `continue`, `reverify`, `salvage`, `supersede`, `defer`, and `cancel`.

  R9. Head changes alone must not invalidate work. The design must support impact-scoped invalidation
  rather than naive “branch head changed, reject everything” behavior.

  R10. Task lifecycle state is orchestrator-owned. Agents may produce artifacts and evidence, but they
  do not decide authoritative pass/fail or mutate task state directly.

  R11. Executor-owned canonical outputs must exist for every attempt: result envelope, command logs,
  artifact records, verification records, and immutable provenance metadata.

  R12. The design must preserve rolling-wave execution: the full logical plan may exist, but detailed
  workspace/materialization should happen just in time for the next valid ready wave.

  ### Multi-agent coordination and integration

  R13. Efficient aggregation of work from 10 to 50 agents: the system must support collecting,
  comparing, validating, rebasing, and integrating many outputs without collapsing into a serial
  bottleneck.

  R14. Conflict handling: define how overlapping edits are detected early, how semantic or textual
  conflicts are surfaced, and how conflicting work is resolved, quarantined, synthesized, or re-planned.

  R15. Incremental integration: outputs must move through staged promotion and validation gates rather
  than one final “big bang” merge.

  R16. Deterministic merge provenance: every integrated result must record which agent produced which
  change, from what base snapshot, under what policy, and with what validation evidence.

  R17. Scalable review/selection: when multiple agents attempt the same or similar task, the system must
  support ranking, deduplication, best-of-N selection, or synthesis with minimal human intervention.

  R18. Failure containment: malicious, broken, or invalid outputs must be quarantined without slowing or
  corrupting unrelated work.

  ### Build-system-specific correctness

  R19. Explicitly cover safe cache sharing and invalidation for Node.js, Python, Rust, C/C++, Bazel, and
  CMake.

  R20. For each ecosystem, distinguish immutable shared artifacts from task-private writable state.

  R21. Explain handling of compiler caches, generated files, configure outputs, toolchain discovery,
  external repository fetching, and lockfile-like dependency state under concurrency.

  R22. Explain whether and how remote cache, remote execution, distributed compilation, or distributed
  build features are used for Bazel/C++ workloads. If avoided, justify why.

  R23. Address native-build hazards explicitly: ABI drift, toolchain variance, nondeterministic outputs,
  host contamination, generated header/source races, and cache poisoning.

  ## Assumptions

  - Linux execution hosts
  - Monorepo or large polyrepo checkout is possible
  - Agents may run build, test, lint, codegen, and repo-local tooling
  - Repositories may mix npm/pnpm/yarn, Python tooling, Cargo, CMake, and Bazel
  - Agents may be assigned independent or overlapping tasks
  - The control plane is trusted
  - Agent runtimes and executed task code are not trusted
  - Git is the source-of-truth VCS unless you strongly justify an alternative

  ## Mandatory scenarios

  Your design must walk through these scenarios concretely:

  1. Zero to first task execution.
  2. Twenty agents starting within the same minute.
  3. Two agents editing overlapping files and one of them touching a protected/shared surface.
  4. One agent crashing mid-write.
  5. The golden base or approved plan/spec head refreshing while agents are still running.
  6. A new change request arriving while one task is verifying and another is implementing.
  7. Two agents attempting the same task and the system selecting or synthesizing a winner.
  8. A task passing local checks but failing integration-stage validation.
  9. A malicious or poisoned cache/input attempt from one task.
  10. Full teardown and garbage collection after completion or abandonment.