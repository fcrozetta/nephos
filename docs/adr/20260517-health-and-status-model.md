# Health and Status Model

- Status: accepted
- Date: 2026-05-17
- Tags: health, status, observability, phase-1, operations

## Context and Problem Statement

Nephos should provide operational transparency.

Users need to understand what exists, what depends on what, and why something is healthy, degraded, blocked, stopped, or unknown.

Raw Kubernetes readiness alone is insufficient because Nephos has platform concepts Kubernetes does not understand:

- Apps
- Service instances
- capabilities
- bindings
- dependency impact
- route intent
- backup status
- reconciliation state

## Decision

Nephos status is Nephos-aware.

Nephos aggregates status from Kubernetes runtime signals and Nephos platform signals.

Health status levels are:

- `unknown`
- `pending`
- `healthy`
- `degraded`
- `blocked`
- `stopped`
- `not_applicable`

Lifecycle state is separate from health status.

Lifecycle states include:

- installed
- running
- stopped
- disabled
- removed
- destroyed

`removed` and `destroyed` are lifecycle states, not health statuses.

Every status must include reasons and/or evidence.

Do not show opaque green/red status without explaining why.

## Aggregation Signals

Nephos may aggregate:

- desired lifecycle state
- reconciliation state
- Kubernetes object existence
- Kubernetes readiness/liveness/conditions
- App runtime status
- Service instance runtime status
- binding resolved/unresolved
- dependency available/blocked
- capability provider selected/missing
- route or ingress known/unknown
- storage presence/status
- backup status

## Phase 1 Scope

Phase 1 status is Nephos-aware but minimal.

Phase 1 should include:

- desired lifecycle state
- reconciliation state
- Kubernetes object existence/readiness
- binding resolved/unresolved
- dependency availability
- route known/unknown
- backup status as `unsupported`
- Service dependent impact

Phase 1 does not need deep app-specific probes.

## Entity Status

Nephos should expose status for:

- Cluster
- App
- Service instance
- Binding
- Capability provider
- Route/Ingress
- Storage resource
- Backup policy/status

## Service Impact

Service status should include dependent App impact.

Example:

- Service instance is healthy
- stopping it would affect three Apps

This impact is not the same as health, but it is operational status users need before lifecycle operations.

## Consequences

Nephos must track both lifecycle state and health status.

Kubernetes readiness is an input, not the whole status model.

Binding and dependency failures can affect Nephos status even when Kubernetes objects are ready.

Backup status participates even in Phase 1 as `unsupported`.

## Notes

Do not implement status as `kubectl get pods` with nicer formatting.

Nephos status must explain platform relationships and blockers.
