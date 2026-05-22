# Controller and Reconciliation Architecture

- Status: accepted
- Date: 2026-05-17
- Tags: controller, reconciliation, cli, api, architecture

## Context and Problem Statement

Nephos needs to reconcile desired platform state into Kubernetes.

The exact implementation shape is not yet decided.

Possible models include:

- CLI-driven local reconciliation
- API-driven reconciliation
- controller running inside the cluster
- hybrid approach

## Decision

Use an API-owned in-process controller/reconciler for Phase 1.

The reconciler reads Nephos desired state from the API/database and reconciles Nephos-owned resources into Kubernetes.

The CLI talks to the Nephos API/local controller.

The CLI must not become a bag of direct Kubernetes mutations.

The reconciler must be implemented behind boundaries that allow later extraction into:

- a separate local daemon
- a worker process
- an in-cluster controller
- a scheduled reconciliation process

Preserve the architecture boundary:

intent -> desired state -> reconcile into Kubernetes

The detailed Phase 1 execution model is accepted in:

```text
docs/adr/20260518-reconciliation-execution-model.md
```

API 0.0.1 uses an in-process background worker with persisted reconciliation requests in SQLite.

API mutations return after desired state and the reconciliation request are committed.

The API should not wait for Kubernetes convergence before returning.

## Drift Policy

Phase 1 should detect and report drift.

Nephos may reconcile Nephos-owned resources when desired state is explicit, especially during lifecycle operations or explicit reconciliation.

Nephos must not mutate Kubernetes resources it does not own.

Nephos-owned runtime resources should be labeled and/or annotated so drift detection and reconciliation can identify ownership.

Nephos-managed Kubernetes resources should use:

```yaml
app.kubernetes.io/managed-by: nephos
```

Nephos-owned relationship metadata uses keys under `nephos.pro/*`.

Nephos desired state remains the source of truth.

Do not use Kubernetes `ownerReferences` to represent App-Service bindings, Service dependents, lifecycle ownership, or Nephos desired-state ownership in Phase 1.

## Considered Options

### CLI-driven local reconciliation

Pros:

- simpler initially
- lower infrastructure overhead
- easier early development

Cons:

- weaker continuous reconciliation
- harder UI/API integration later
- less platform-like

### API-driven reconciliation

Pros:

- cleaner product architecture
- supports CLI and UI
- centralizes platform state

Cons:

- requires API and persistence earlier

### In-cluster controller

Pros:

- Kubernetes-native
- continuous reconciliation
- strong runtime ownership

Cons:

- heavier early implementation
- risks CRD/operator complexity too soon

## Status Notes

This decision is accepted.

Implementation can start pragmatic, but must not violate the conceptual boundary.
