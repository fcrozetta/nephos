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

## State Model

Nephos owns desired platform state.

The canonical state path is:

intent -> API/database desired state -> reconciler -> Kubernetes runtime state

YAML is import/export only.

Kubernetes CRDs and GitOps-as-source-of-truth are deferred until explicit future decisions.
