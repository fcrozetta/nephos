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

## Drift Policy

Phase 1 should detect and report drift.

Nephos may reconcile Nephos-owned resources when desired state is explicit, especially during lifecycle operations or explicit reconciliation.

Nephos must not mutate Kubernetes resources it does not own.

Nephos-owned runtime resources should be labeled and/or annotated so drift detection and reconciliation can identify ownership.

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
