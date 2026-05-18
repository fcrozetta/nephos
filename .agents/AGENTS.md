# Agent Instructions for Nephos

Nephos is a personal/local platform control plane, not a Portainer clone.

The core model is:

- Apps: user-facing workloads/products.
- Services: shared platform capabilities/infrastructure.
- Capabilities: typed abilities exposed by Services and consumed by Apps.
- Runtime: K3s/Kubernetes substrate.

Do not use "plugin" for shared infrastructure. Use "Service".

Default backend: K3s.

Other Kubernetes backends may be added later through cluster adapters, but K3s is the primary real backend.

Nephos owns platform intent, catalogs, service binding, lifecycle state, dependency resolution, secrets injection policy, health/status, backups semantics, and ingress abstraction.

Kubernetes owns runtime primitives: Deployments, StatefulSets, Services, Ingress, PVCs, Secrets, ConfigMaps, Jobs, CronJobs, probes, scheduling, networking.

Do not turn Nephos into a generic container UI.
The differentiator is composable self-hosted infrastructure: Apps & Services, capability binding, and platform-level relationships.

Before making architectural changes, read the current architecture context, including `.agents/context/nephos-naming-and-metadata.md`, plus `docs/adr/`.

Before writing or changing architecture context or ADR files, tell Fer explicitly which context files or ADRs need to change and why.

Do not silently add, accept, or reshape architectural decisions in `.agents/context/`, `docs/adr/`, `examples/`, or `schemas/`.

If Fer has not selected a decision, keep it in `.agents/context/nephos-open-questions.md` or in a draft ADR.

Create or update an ADR when a change affects architecture structure, lifecycle semantics, source of truth, manifest/schema shape, runtime boundaries, auth/security, backup/data lifecycle semantics, public API/CLI contract, catalog behavior, or Phase 1 scope.

Use ADR statuses consistently:

- `draft`: unresolved or exploratory
- `proposed`: candidate direction awaiting Fer confirmation
- `accepted`: Fer confirmed the decision
- `rejected`: explicitly not chosen
- `deprecated`: no longer recommended
- `superseded`: replaced by a later ADR

If architecture is unclear, ask Fer or record an open question before implementing.

Low-level implementation details may be chosen pragmatically when consistent with accepted ADRs and context.

Do not add canonical schema files under `schemas/` until Fer approves the concrete validation schema, or canonical examples under `examples/` until Fer approves the manifest/example shape.

Temporary draft manifests are allowed during schema design, but they must live in `.agents/drafts/manifests/`, be labeled non-canonical, and not be treated as source of truth.

Draft manifests must be deleted, moved, or converted after Fer accepts the schema/example shape.

Any change that alters architecture or public contracts must update ADRs, context, or open questions in the same change.

Keep architecture decision batches in separate commits when feasible.
