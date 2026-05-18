## Nephos Agent Guide

### Overview

Nephos is a platform control plane for composable self-hosted infrastructure.

Nephos manages:

- Apps
- Services
- Capabilities
- Bindings
- Platform lifecycle

Nephos intentionally operates above raw container/runtime orchestration abstractions.

The goal is to provide a unified platform experience for self-hosted infrastructure while remaining local-first, developer-friendly, and operationally transparent.

---

## Core Concepts

### Apps

Apps are user-facing workloads/products.

Examples include:

- media systems
- source control platforms
- document management systems
- dashboards
- personal cloud applications
- AI applications

Apps:

- consume capabilities exposed by Services
- may expose ingress/routes
- may persist data
- may depend on one or more Services
- are installable/removable independently

---

### Services

Services are shared platform infrastructure/capabilities.

Examples include:

- PostgreSQL
- Redis
- Object Storage
- Search engines
- Graph databases
- Queues
- SMTP
- Authentication providers
- AI inference backends

Services:

- expose capabilities
- may be shared across Apps
- may provision app-scoped resources
- are lifecycle-managed by Nephos

Do not refer to Services as plugins.

---

### Capabilities

Capabilities are typed platform features exposed by Services and consumed by Apps.

Examples:

- postgres
- sql
- redis
- s3
- graph-db
- document-db
- search
- kv
- smtp
- auth

Apps should depend on capabilities rather than concrete infrastructure whenever possible.

---

## Runtime Model

### Default Runtime

Nephos targets Kubernetes as its runtime substrate.

Default backend:

- K3s

Other Kubernetes backends may be supported later through cluster adapters.

Examples:

- kind
- minikube
- external kubeconfig environments

Kubernetes compatibility primarily exists above the Kubernetes API layer.

Cluster lifecycle management remains backend-specific.

---

## Ownership Boundary

### Nephos Owns

Nephos owns:

- app catalog
- service catalog
- dependency resolution
- capability binding
- resource provisioning
- secrets injection policy
- lifecycle state
- health/status aggregation
- ingress abstraction
- backup semantics
- platform relationships

---

### Kubernetes Owns

Kubernetes owns:

- scheduling
- networking primitives
- deployments/statefulsets
- services
- PVCs
- secrets/configmaps
- ingress resources
- health probes
- runtime orchestration

Nephos should not reimplement Kubernetes behavior.

---

## Command Model

### Cluster Commands

Cluster commands manage the Kubernetes substrate itself.

Examples:

```bash
nephos cluster init
nephos cluster up
nephos cluster down
nephos cluster status
nephos cluster destroy
```

---

### App Commands

App commands manage user-facing workloads.

Examples:

```bash
nephos app install
nephos app start
nephos app stop
nephos app remove
nephos app destroy
```

---

### Service Commands

Service commands manage shared platform infrastructure.

Examples:

```bash
nephos service install
nephos service start
nephos service stop
nephos service remove
nephos service destroy
```

Stopping Services should be dependency-aware.

---

## Lifecycle Semantics

Lifecycle operations modify desired state and reconcile into Kubernetes.

Lifecycle operations should not map directly to raw Kubernetes deletion commands.

---

### stop

Stopping an App should:

- scale workloads to zero
- suspend scheduled jobs where applicable
- preserve data and metadata

Stopping should preserve:

- PVCs
- Secrets
- ConfigMaps
- bindings
- backups
- service relationships
- lifecycle metadata

---

### start

Restore previous desired runtime state.

---

### disable

Prevent automatic reconciliation/startup.

---

### remove

Remove deployed runtime objects while optionally preserving persistent data.

---

### destroy

Delete all runtime objects and persistent data.

---

## Architectural Guardrails

Nephos is a platform control plane, not Kubernetes exposed directly to users.

Kubernetes is the runtime substrate.
Nephos owns platform intent, relationships, lifecycle semantics, and capability binding.

The core differentiator is composable self-hosted infrastructure through Apps, Services, capabilities, bindings, and platform-level relationships.

Do not turn Nephos into generic container/runtime management.
Do not tie Nephos directly to any external deployment platform.

---

## Architectural Direction

Nephos is designed around:

- composable infrastructure
- platform-level relationships
- capability binding
- operational transparency
- local-first infrastructure ownership

The core abstraction is:

- Apps consume capabilities exposed by Services.

---

### Context Loading

Before making architectural changes, read:

- `.agents/context/nephos-vision.md`
- `.agents/context/nephos-glossary.md`
- `.agents/context/nephos-architecture.md`
- `.agents/context/nephos-api-resource-model.md`
- `.agents/context/nephos-database-state.md`
- `.agents/context/nephos-decisions.md`
- `.agents/context/nephos-naming-and-metadata.md`
- `.agents/context/nephos-open-questions.md`
- `docs/adr/`

For multi-step implementation work, create or update a plan using `PLANS.md` before editing code.

Do not infer missing architecture. If a decision is not documented, record it as an open question before implementing.

### Architecture Documentation Writes

Before writing or changing architecture context or ADR files, tell Fer explicitly which context files or ADRs need to change and why.

Do not silently add, accept, or reshape architectural decisions in `.agents/context/`, `docs/adr/`, `examples/`, or `schemas/`.

If Fer has not selected a decision, keep it in `.agents/context/nephos-open-questions.md` or in a draft ADR.

### ADR Requirements

Create or update an ADR when a change affects:

- architecture structure
- lifecycle semantics
- source of truth
- manifest or schema shape
- runtime boundaries
- auth or security model
- backup or data lifecycle semantics
- public API or CLI contract
- catalog behavior
- Phase 1 scope

Use ADR statuses consistently:

- `draft`: unresolved or exploratory
- `proposed`: candidate direction awaiting Fer confirmation
- `accepted`: Fer confirmed the decision
- `rejected`: explicitly not chosen
- `deprecated`: no longer recommended
- `superseded`: replaced by a later ADR

Accepted ADRs are durable. Material changes to accepted decisions should normally create a new ADR that supersedes or amends the earlier decision.

### Agent Uncertainty Rule

If architecture is unclear, ask Fer or record an open question before implementing.

Low-level implementation details may be chosen pragmatically when they are consistent with accepted ADRs and context.

### Schema And Example Workflow

Do not add canonical schema files under `schemas/` until Fer approves the concrete validation schema.

Do not add canonical examples under `examples/` until Fer approves the manifest or example shape.

Temporary draft manifests are allowed while designing schemas, but they must live in `.agents/drafts/manifests/`, be labeled non-canonical, and not be treated as source of truth.

Draft manifests must be deleted, moved, or converted after Fer accepts the schema/example shape.

### Change Discipline

Any PR, commit, or agent change that alters architecture or public contracts must update ADRs, context, or open questions in the same change.

Keep architecture decision batches in separate commits when feasible.

---

## Documentation

Detailed architecture and decision records are located in:

```text
.agents/context/
docs/adr/
```

Agents working on Nephos should consult those documents before making architectural changes.
