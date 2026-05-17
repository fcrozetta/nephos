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
