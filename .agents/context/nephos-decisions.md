# Nephos Decisions

## D001: Nephos is a platform control plane

Nephos is a platform control plane for composable self-hosted infrastructure.

It should not be modeled as a generic container manager.

## D002: K3s is the default runtime backend

K3s is the primary runtime backend.

Other Kubernetes backends may be supported later through cluster adapters.

## D003: Kubernetes is the runtime API boundary

Nephos can be backend-agnostic mostly above the Kubernetes API layer.

Below that layer, cluster lifecycle is backend-specific.

## D004: Apps and Services are top-level concepts

Nephos has two primary installable concepts:

- Apps
- Services

Apps are user-facing workloads.

Services are shared platform infrastructure/capabilities.

## D005: Services expose capabilities

Services expose typed capabilities.

Apps consume capabilities through bindings.

## D006: Nephos API/database is canonical desired state

The Nephos API and database are the source of truth for desired platform state.

SQLite is the Phase 1 database.

YAML is import/export only.

Kubernetes is runtime state.

Kubernetes CRDs and GitOps-as-source-of-truth are deferred.

## D007: Backend and CLI live in separate repositories

The `nephos` repository owns the backend/control plane.

The CLI lives in `../nephos-cli` and `https://github.com/fcrozetta/nephos-cli`.

Do not implement CLI code in this repository without an explicit decision changing that boundary.

## D008: Phase 1 backend stack

The backend stack is Python, FastAPI, SQLite, simple explicit SQL migrations, and the official Python Kubernetes client.

## D009: Phase 1 CLI stack

The CLI stack is Python and Typer, implemented in the separate `nephos-cli` repository.

The CLI talks to the Nephos API/local controller.

The CLI must not become an unstructured direct Kubernetes mutation layer.

## D010: Phase 1 reconciler shape

Use an API-owned in-process reconciler for Phase 1.

Keep module boundaries clear enough to later extract the reconciler into a daemon, worker, scheduled process, or in-cluster controller.

Phase 1 drift handling should detect and report drift and reconcile only Nephos-owned resources when desired state is explicit.

## D011: Nephos manifests are the package boundary

Installable Apps and Services are defined by Nephos manifests.

Nephos manifests own platform semantics.

Helm charts and raw Kubernetes manifests are runtime deployment implementation details underneath the Nephos manifest layer.

## D012: App and Service manifests are separate

Apps and Services use separate manifest formats because they have different roles and authors.

App authors should not need to understand Service internals.

Service authors need to model capability exposure, provisioning behavior, and Service operations.

## D013: Helm-primary runtime packaging

Helm charts are the primary Phase 1 runtime deployment mechanism underneath Nephos manifests.

Raw Kubernetes manifests are an allowed fallback when no credible chart exists, a chart is too leaky or unstable, the workload is simple, Nephos deploys its own support components, or a curated Nephos-native deployment is clearer.

## D014: Local filesystem catalog first

Phase 1 catalogs start as local filesystem catalogs.

Git repositories, OCI registries, remote indexes, signed catalogs, and private remote catalogs are deferred.

## D015: Service operation terminology

Service operation is the canonical term for typed backend/API-owned Service management actions.

Service management action may be used descriptively, but should not be the preferred architecture term.

Service operations are optional in Phase 1, and their detailed contract still needs design.

## D016: Installed Services are Service instances

Service instance is the canonical term for an installed concrete Service.

A Service manifest defines an installable Service shape.

A Service instance is the installed platform/runtime instance.

## D017: Services are shared by default

Services are shared by default.

Where a Service supports app-scoped resources inside one runtime instance, Nephos should use one shared Service instance by default.

PostgreSQL should generally use one shared Service instance with separate databases/users per App by default.

## D018: Dedicated Service instances are reserved

Apps may request isolation from a Service provider.

An isolation request creates a dedicated Service instance when required or requested.

Dedicated Service instances are still first-class Services and may be explicitly bound by other Apps.

Phase 1 reserves the concept but implements shared/global Service instances first.

## D019: Bindings track dependents

Bindings are the source of dependent tracking between Apps and Service instances.

Do not maintain ad hoc dependent lists as authoritative state.

## D020: Service provider selection rules

Multiple Service instances may expose the same capability.

If exactly one eligible Service instance exposes a required capability, Nephos may auto-bind by default.

If multiple eligible Service instances expose a required capability and no default provider is configured, Nephos must require explicit selection.

Nephos may support a user-configurable default provider per capability.

## D021: Service lifecycle with dependents requires force

Stopping, removing, or destroying a Service instance with dependents must require explicit force and show an impact list.

Shared Service instances are long-lived infrastructure by default.

## D022: No Phase 1 resource policy system

Phase 1 does not implement a Nephos resource policy system.

Running Apps and Services use replicas `1`.

Stopped or disabled Apps and Services use replicas `0`.

Resource profiles are reserved for future design but not defined.

Raw Kubernetes CPU/memory knobs are not primary UX.

## D023: No Phase 1 HA or autoscaling

Phase 1 does not support HA, autoscaling, affinity, anti-affinity, quotas, or scheduling policy.

## D024: Phase 1 auth is single-owner local-first

Phase 1 is single-owner and local-first.

The CLI is a trusted local client.

No login, multi-user model, roles, or RBAC are required in Phase 1.

The Web UI is deferred.

Friend, cloud, hosted, and multi-user scenarios are out of scope for Phase 1 but not forbidden forever.

## D025: Versions are pinned and upgrades are manual

App, Service, catalog, Helm chart, runtime deployment reference, and Nephos versions are pinned.

Upgrades are explicit and manual.

No automatic latest behavior is allowed by default.

## D026: Service upgrades with persistent data are risky by default

Services are higher-risk upgrade targets than Apps because they commonly own persistent infrastructure state.

Risky Service upgrades should require backup/checkpoint confirmation once the Service declares backup support.

Until backup support exists, Nephos must warn that no supported backup exists.

Rollback is best-effort in Phase 1, not guaranteed.

## D027: Nephos owns backup intent but not universal implementation

Nephos owns backup intent, policy, and status.

Services own or provide data-aware backup/restore implementation where data semantics matter.

Phase 1 does not implement concrete backup/restore and must not promise universal backup guarantees.

## D028: Destroy is the data-deleting lifecycle operation

Stop preserves persistent data.

Remove removes runtime objects while preserving persistent data by default.

Destroy deletes runtime objects and persistent data.

Destroy must require destructive confirmation when persistent data exists.

There is no separate purge lifecycle operation.

## D029: Health status is Nephos-aware

Nephos health/status aggregates Kubernetes runtime signals and Nephos platform signals.

Kubernetes readiness is an input, not the full status model.

## D030: Lifecycle state is separate from health status

Removed and destroyed are lifecycle states, not health statuses.

Health status levels are `unknown`, `pending`, `healthy`, `degraded`, `blocked`, `stopped`, and `not_applicable`.

## D031: Status requires reasons and evidence

Every status must include reasons and/or evidence.

Do not expose opaque green/red status without explaining why.

## D032: Phase 1 status is minimal but platform-aware

Phase 1 status includes desired lifecycle state, reconciliation state, Kubernetes object existence/readiness, binding resolution, dependency availability, route known/unknown, backup status as `unsupported`, and Service dependent impact.

## D033: Phase 1 targets single-node K3s

Phase 1 targets single-node K3s as the default real runtime backend.

Cluster lifecycle support is minimal in Phase 1.

## D034: Phase 1 App and Service lifecycle commands

Phase 1 includes App and Service install, start, stop, remove, and destroy.

The disable lifecycle operation is deferred.

## D035: Phase 1 uses local filesystem catalog from day one

Phase 1 should load a local filesystem catalog from day one.

The repo may ship a tiny reference catalog, but App behavior must not be hardcoded in backend logic.

## D036: No service mesh in Phase 1

Multi-component Apps communicate through normal Kubernetes Services/networking.

No service mesh is required or included in Phase 1.

## D037: Paperless and PostgreSQL reference scenario

The canonical Phase 1 reference scenario is Paperless App plus PostgreSQL Service.

## D038: One namespace per App or Service instance

Nephos uses separate Kubernetes namespaces for App instances and Service instances.

Use `app-<slug>` for App instances, `svc-<slug>` for Service instances, and `nephos-system` for Nephos control-plane/runtime support components.

Remove preserves namespaces.

Destroy deletes namespaces by default after destructive confirmation when persistent data exists.

## D039: No default-deny NetworkPolicy in Phase 1

Phase 1 does not apply default-deny NetworkPolicy.

Network policy is reserved for later design.

## D040: Traefik local ingress in Phase 1

Traefik is the Phase 1 default ingress controller because K3s includes it.

Nephos owns route and visibility intent.

Kubernetes owns concrete Ingress resources.

Phase 1 implements local visibility and reserves private, public, and tailnet visibility for later.

## D041: Manual tunnel compatibility without tunnel automation

Cloudflare Tunnel, Tailscale, DNS automation, and TLS automation are deferred.

Nephos-generated local ingress must be compatible with a manually configured Cloudflare Tunnel, but Nephos does not manage Cloudflare credentials, tunnel lifecycle, or DNS records in Phase 1.

## D042: Stopped Apps keep route intent

Stopping an App keeps route intent and may keep runtime ingress objects.

Status must report the App as stopped or unavailable.

Removing or destroying an App removes runtime ingress objects.

## D043: Kubernetes Secrets are Phase 1 secret storage

Phase 1 uses Kubernetes Secrets.

External secret managers are deferred.

Nephos owns secret policy, labels, injection, preservation, deletion, and redaction semantics.

## D044: Binding credentials are materialized into App namespaces

Service-internal and Service-admin secrets live in Service instance namespaces.

App binding credentials are materialized into App namespaces.

Apps should not read Service namespace Secrets directly.

Bindings determine which App may receive which Service credentials.

## D045: Secret values are redacted by default

Secret values must be redacted in API responses, CLI output, status output, logs, and diagnostics by default.

Stop and remove preserve Secrets.

Destroy deletes Secrets for the destroyed entity after destructive confirmation when persistent data or credentials are involved.

## D046: Phase 1 catalog sources are local filesystem paths

Phase 1 supports repo-shipped reference catalog entries and user-configured local filesystem catalog paths.

The backend must not hardcode App or Service behavior.

Reference scenarios should exercise the catalog and manifest path.

## D047: User-created local catalog entries are allowed

User-created local catalog entries are allowed in Phase 1.

Until the manifest schema is accepted, local user-created entries do not carry a schema stability promise.

## D048: Local catalog files are trusted local-owner input

Phase 1 treats local catalog files as trusted local-owner input.

Remote catalog trust, signing, verification, private catalog credentials, and package sandboxing guarantees are deferred.

## D049: Catalog metadata lives in manifests for Phase 1

For Phase 1, App and Service manifests carry minimal catalog metadata.

A separate catalog index is deferred.

Catalog metadata must not become a second source of truth for package semantics.

## D050: Backend local development uses uv

Use `uv` as the canonical Python workflow for backend development in this repository.

## D051: Backend tests use pytest and ruff

Use `pytest` for backend tests.

Use `ruff` for backend linting/formatting checks.

Use mocks or fakes for unit tests.

Use real K3s for Kubernetes integration tests.

## D052: Phase 1 backend distribution is local process plus container image

Phase 1 backend distribution consists of a local development process and a backend container image for runtime packaging.

Full installer packaging is deferred.

## D053: CLI workflow belongs to the CLI repository

The separate `nephos-cli` repository owns CLI implementation, linting, testing, packaging, and release workflow.

Do not add CLI implementation code to this repository without an explicit boundary change.

## D054: Phase 1 has version awareness without strict blocking

The backend should expose a version endpoint.

The CLI should report CLI and backend versions and may warn when backend version is unknown, older, or newer than expected.

The CLI should not block state-mutating commands solely because of version mismatch in Phase 1.

Strict CLI/backend compatibility blocking is deferred.

## D055: ADRs are required for architecture-significant changes

Create or update ADRs for changes affecting architecture structure, lifecycle semantics, source of truth, manifest/schema shape, runtime boundaries, auth/security, backup/data lifecycle semantics, public API/CLI contract, catalog behavior, or Phase 1 scope.

Minor implementation details inside accepted architecture do not require a new ADR.

## D056: ADR statuses have explicit meanings

Use `draft`, `proposed`, `accepted`, `rejected`, `deprecated`, and `superseded`.

`accepted` means Fer confirmed the decision.

Accepted ADRs are durable.

Material changes to accepted decisions should normally use a new superseding/amending ADR.

## D057: Agents must not implement through architectural ambiguity

If architecture is unclear, agents must ask Fer or record an open question before implementing.

Low-level implementation details may be chosen pragmatically when consistent with accepted ADRs and context.

## D058: Canonical schemas and examples require Fer approval

Do not add canonical schema files under `schemas/` until Fer approves the concrete field schema.

Do not add canonical examples under `examples/` until Fer approves the manifest or example shape.

Temporary draft manifests are allowed while designing schemas, but they must live under `.agents/drafts/manifests/`, be clearly marked non-canonical, and not be treated as source of truth.

## D059: Architecture-changing work updates documentation in the same change

Any PR, commit, or agent change that alters architecture or public contracts must update ADRs, context, or open questions in the same change.

## D060: Keep architecture decision batches separate when feasible

Keep architecture decision batches in separate commits when feasible.

## D061: Draft manifest workspace is .agents/drafts/manifests

Temporary draft manifest sketches may live under `.agents/drafts/manifests/`.

Draft manifests are non-canonical, must not live under `schemas/` or `examples/`, and must not be treated as source of truth.

## D062: Paperless plus PostgreSQL is the canonical reference scenario flow

The canonical Phase 1 reference scenario installs PostgreSQL Service, installs Paperless App, binds Paperless to the `postgres` capability, exposes Paperless through local route intent, exercises stop/start data preservation, removes Paperless preserving data, and destroys Paperless with destructive confirmation.

Paperless requires only PostgreSQL in the Phase 1 reference scenario.

## D063: Reference scenario includes Service dependency impact

The reference scenario must include attempting to stop PostgreSQL while Paperless depends on it.

Nephos should block the Service stop unless forced and show an impact list.

## D064: Reference scenario route is illustrative

Use an illustrative local route such as `paperless.<local-domain>`.

The exact local domain, wildcard behavior, DNS behavior, and TLS behavior remain open.

## D065: Nephos manifests use YAML

Nephos manifests are YAML documents.

## D066: Nephos manifests use a Kubernetes-like envelope

Nephos manifests use `apiVersion`, `kind`, `metadata`, and `spec`.

The envelope is for Nephos manifest structure and versioning.

It does not mean Nephos manifests are Kubernetes CRDs.

## D067: App and Service are accepted manifest kinds

Accepted manifest kinds are `App` and `Service`.

Apps and Services remain separate because they have different roles and authors.

## D068: Runtime references remain below Nephos manifests

Phase 1 remains Helm-primary underneath Nephos manifests.

Helm runtime references should carry pinned chart identity such as repository, chart name, and chart version.

Raw Kubernetes manifest references remain an allowed fallback.

Raw Helm values and Kubernetes object specs must not become the primary Nephos manifest schema.

## D069: Binding schema remains minimal at manifest level

App manifests declare required capabilities.

Service manifests declare exposed capabilities.

Nephos resolves and creates bindings outside the manifest.

Concrete binding field names remain open.
