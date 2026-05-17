# Namespace Strategy

- Status: accepted
- Date: 2026-05-17
- Tags: kubernetes, namespaces, isolation, runtime, phase-1

## Context and Problem Statement

Nephos needs a Kubernetes namespace strategy for Apps, Services, and control-plane components.

Namespaces affect isolation, lifecycle operations, debugging, resource ownership, and cleanup behavior.

## Decision

Use separate Kubernetes namespaces for Nephos control-plane components, App instances, and Service instances.

Namespace pattern:

- `nephos-system` for Nephos control-plane/runtime support components
- `app-<slug>` for an App instance
- `svc-<slug>` for a Service instance

Example:

- nephos-system
- app-paperless
- app-immich
- svc-postgres
- svc-redis
- svc-arangodb

An App instance and a Service instance must not share a namespace by default.

Shared Service instances remain in Service namespaces, even when several Apps bind to them.

Dedicated Service instances also remain Service instances and use Service namespaces.

## Lifecycle Behavior

`remove` preserves the namespace.

`destroy` deletes the namespace by default after destructive confirmation when persistent data exists.

This matches the broader lifecycle model:

- stop preserves runtime metadata and persistent state
- remove removes deployed runtime objects while preserving persistent data
- destroy deletes runtime objects and persistent data

## Network Policy

Phase 1 does not enable default-deny NetworkPolicy by default.

Network policy is reserved for later design.

Do not silently introduce default-deny behavior in Phase 1 because it can break App-to-Service binding, multi-component Apps, ingress, and controller access before Nephos has a proper policy model.

## Rationale

Separate namespaces make ownership and lifecycle boundaries clearer.

App lifecycle operations should not accidentally affect shared Services.

Service lifecycle operations require dependency awareness.

Namespace separation also makes debugging and cleanup easier without requiring Nephos to become a Kubernetes dashboard.

## Open Questions

Need to decide:

- exact slug normalization and collision handling
- exact labels and annotations applied to namespaces
- future NetworkPolicy model
- exact cross-namespace connection metadata exposed through bindings

## Consequences

One namespace per App/Service instance is more verbose than a single shared namespace, but it keeps ownership boundaries explicit.

Nephos must track namespace ownership and lifecycle state in desired state.

Kubernetes namespace deletion is destructive, so Nephos must gate destroy operations when persistent data exists.

## Status Notes

Do not place all Apps and Services into a single namespace without revisiting this decision.
