# Nephos Architecture

## High-Level Architecture

Nephos is a platform control plane over Kubernetes.

Architecture:

Nephos CLI
-> Nephos API
-> Nephos Controller / Reconciler
-> Kubernetes Runtime

The Web UI is deferred for Phase 1.

Default runtime backend:

- K3s

## Repository Boundaries

This repository, `nephos`, owns the backend control plane:

- API
- desired-state persistence
- reconciliation orchestration
- platform model
- catalog model
- architecture context and ADRs

The CLI is a separate repository:

- GitHub: `https://github.com/fcrozetta/nephos-cli`
- Local path: `../nephos-cli`

Do not add CLI implementation code to this repository without an explicit decision changing that boundary.

## Main Components

### CLI

The CLI is the primary early user interface.

The CLI is implemented in `../nephos-cli`.

The CLI talks to the Nephos API/local controller.

The CLI must not become an unstructured direct Kubernetes mutation layer.

Phase 1 has backend/CLI version awareness but no strict compatibility blocking.

The backend should expose a version endpoint.

The CLI should report CLI and backend versions and may warn on unknown/newer/older backend versions.

The CLI should not block state-mutating commands solely because of version mismatch in Phase 1.

It should support:

- nephos cluster *
- nephos app *
- nephos service *

### API

The API should own platform intent.

The API/database is the canonical source of desired platform state.

For Phase 1, the backend stack is:

- Python
- FastAPI
- SQLite
- simple explicit SQL migrations
- `uv` local development workflow
- `pytest` backend tests
- `ruff` backend linting/formatting checks

Backend unit tests should use mocks/fakes.

Kubernetes integration tests should run against real K3s.

### Controller / Reconciler

The controller reconciles Nephos desired state into Kubernetes resources.

For Phase 1, the controller/reconciler is API-owned and in-process.

The reconciler should be isolated behind module boundaries so it can later move to a daemon, worker, or in-cluster controller.

Phase 1 should detect and report drift.

Nephos may reconcile Nephos-owned resources when desired state is explicit, but must not mutate Kubernetes resources it does not own.

### Kubernetes Runtime

Kubernetes owns runtime execution.

It owns:

- scheduling
- networking primitives
- Deployments
- StatefulSets
- Services
- Ingress
- PVCs
- Secrets
- ConfigMaps
- Jobs
- CronJobs
- probes

Nephos should use Kubernetes, not reimplement it.

### Runtime Boundaries

Nephos uses separate Kubernetes namespaces for App instances, Service instances, and control-plane components.

Namespace pattern:

- `nephos-system`
- `app-<slug>`
- `svc-<slug>`

`remove` preserves namespaces.

`destroy` deletes namespaces by default after destructive confirmation when persistent data exists.

Phase 1 does not enable default-deny NetworkPolicy.

Traefik is the Phase 1 default ingress controller because K3s includes it by default.

Nephos owns route and visibility intent.

Kubernetes owns concrete Ingress resources.

Phase 1 implements local visibility.

Public/private/tailnet exposure, Cloudflare Tunnel automation, Tailscale automation, DNS automation, and TLS automation are deferred.

Nephos-generated local ingress should be compatible with a manually configured Cloudflare Tunnel.

Phase 1 uses Kubernetes Secrets.

Service-internal/admin secrets live in Service namespaces.

App binding credentials are materialized into App namespaces.

Secret values must be redacted in API responses, CLI output, status output, logs, and diagnostics by default.

## Catalog Layer

Nephos should have two catalogs:

- App Catalog
- Service Catalog

Apps declare required capabilities.

Services declare exposed capabilities.

Nephos resolves App requirements to installed or installable Services.

Phase 1 catalog source is local filesystem first.

Supported Phase 1 catalog sources are repo-shipped reference entries and user-configured local filesystem paths.

User-created local catalog entries are allowed in Phase 1, but there is no schema stability promise until the manifest schema is accepted.

Phase 1 treats local catalog files as trusted local-owner input.

Git, OCI, remote indexes, signed catalogs, private remote catalogs, and remote trust policy are deferred.

For Phase 1, App and Service manifests carry minimal catalog metadata.

A separate catalog index is deferred.

## Packaging Layer

Nephos uses separate Nephos manifest formats for Apps and Services.

Nephos manifests own platform semantics.

Nephos manifests are YAML documents using a Kubernetes-like envelope with Nephos semantics:

- `apiVersion`
- `kind`
- `metadata`
- `spec`

Accepted manifest kinds are `App` and `Service`.

This does not make Nephos manifests Kubernetes CRDs.

Helm charts are the primary Phase 1 runtime deployment mechanism underneath Nephos manifests.

Raw Kubernetes manifests are a fallback runtime deployment mechanism.

Helm values and Kubernetes object specs must not become the primary Nephos UX.

Service manifests may expose optional Service operations.

Service operation is the canonical term for typed Service management actions.

## Service Ownership Model

Installed concrete Services are Service instances.

Services are shared by default.

Shared Service instances are expected to serve multiple Apps through bindings.

Where supported, a shared Service instance should provision app-scoped resources inside one runtime instance.

Example:

- one PostgreSQL Service instance
- separate database/user per App
- separate binding per App requirement

Apps may request isolation from a Service provider.

An isolation request creates a dedicated Service instance when required or explicitly requested.

Dedicated Service instances are still first-class Services.

Dedicated Service instances may be explicitly bound by other Apps when integration between Apps requires access to the same provider.

Phase 1 supports shared/global Service instances first and reserves dedicated Service instances as a concept.

Multiple Service instances may expose the same capability.

If exactly one eligible Service instance exposes a required capability, Nephos may auto-bind by default.

If multiple eligible Service instances expose a required capability and no default provider is configured, Nephos must require explicit selection.

Nephos may support a user-configurable default provider per capability.

Bindings are the source of dependent tracking.

Stopping, removing, or destroying a Service instance with dependents must require explicit force and show an impact list.

## State Model

Nephos owns desired platform state.

The canonical state path is:

intent -> API/database desired state -> reconciler -> Kubernetes runtime state

YAML is import/export only.

Kubernetes CRDs and GitOps-as-source-of-truth are deferred until explicit future decisions.

## Resource Policy

Phase 1 does not implement a Nephos resource policy system.

Running Apps and Services use replicas `1`.

Stopped or disabled Apps and Services use replicas `0`.

Resource profiles are reserved for future design but not defined.

Nephos does not expose raw Kubernetes CPU/memory requests and limits as primary UX in Phase 1.

No HA, autoscaling, affinity, anti-affinity, quotas, or scheduling policy are supported in Phase 1.

## Auth Model

Phase 1 is single-owner and local-first.

The CLI is a trusted local client.

No login, multi-user model, roles, or RBAC are required in Phase 1.

The Web UI is deferred.

Friend, cloud, hosted, and multi-user scenarios are out of scope for Phase 1 but not forbidden forever.

## Development And Distribution

This repository owns backend/control-plane development workflow.

The CLI repository owns CLI linting, testing, packaging, and release workflow.

Phase 1 backend distribution is a local development process plus backend container image.

Full installer packaging is deferred.
