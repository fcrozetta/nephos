# Desired State Reconciliation

- Status: accepted
- Date: 2026-05-17
- Tags: reconciliation, lifecycle, state, kubernetes

## Context and Problem Statement

Nephos lifecycle commands could be implemented as direct Kubernetes mutations.

That would be simple initially, but would make Nephos a thin command wrapper over Kubernetes.

Nephos needs to preserve platform intent and reconcile runtime state from that intent.

## Decision

Nephos lifecycle commands update desired platform state.

Nephos reconciles desired platform state into Kubernetes resources.

Lifecycle commands must not map naively to raw Kubernetes operations such as `kubectl delete`.

## Rationale

Nephos owns platform intent.

Kubernetes owns runtime execution.

Desired state lets Nephos preserve metadata, relationships, bindings, backup semantics, lifecycle state, and future policy decisions.

## Consequences

Nephos needs a state model.

Nephos needs reconciliation logic.

The CLI should not become an unstructured bag of direct Kubernetes mutations.

The implementation may start simple, but the architecture boundary must remain:

intent -> desired state -> reconcile into Kubernetes

## Notes

This decision is foundational.

If Nephos loses desired state, it collapses toward runtime plumbing.
