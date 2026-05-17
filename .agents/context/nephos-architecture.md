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

## Catalog Layer

Nephos should have two catalogs:

- App Catalog
- Service Catalog

Apps declare required capabilities.

Services declare exposed capabilities.

Nephos resolves App requirements to installed or installable Services.

Phase 1 catalog source is local filesystem first.

Git, OCI, remote indexes, signed catalogs, and private remote catalogs are deferred.

## Packaging Layer

Nephos uses separate Nephos manifest formats for Apps and Services.

Nephos manifests own platform semantics.

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
