# Nephos Health And Status

## Core Decision

Nephos status is Nephos-aware.

Nephos aggregates status from:

- Nephos desired state
- reconciliation state
- Kubernetes runtime state
- bindings
- dependencies
- routes
- storage
- backup status

Kubernetes readiness is an input, not the whole status model.

## Health Status

Health status answers whether an entity that should be operating is operating correctly.

Accepted health status levels:

- `unknown`
- `pending`
- `healthy`
- `degraded`
- `blocked`
- `stopped`
- `not_applicable`

Every status must include reasons and/or evidence.

Do not show opaque green/red status without explaining why.

## Lifecycle State

Lifecycle state answers what Nephos intends or has done with the entity.

Lifecycle states include:

- installed
- running
- stopped
- disabled
- removed
- destroyed

`removed` and `destroyed` are lifecycle states, not health statuses.

For removed or destroyed entities, health is usually `not_applicable`.

## Phase 1 Scope

Phase 1 status is Nephos-aware but minimal.

Include:

- desired lifecycle state
- reconciliation state
- Kubernetes object existence/readiness
- binding resolved/unresolved
- dependency availability
- route known/unknown
- canonical route URL and alias URLs for Apps with routes
- backup status as `unsupported`
- Service dependent impact

Do not implement deep app-specific probes in Phase 1 unless a specific App or Service requires it later.

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

## Status Reasons And Evidence

A status should include enough explanation to answer why.

Examples:

- `blocked`: required `postgres` capability has no eligible Service instance
- `degraded`: Kubernetes Deployment exists but available replicas are below desired
- `pending`: reconciliation has not created runtime objects yet
- `stopped`: desired lifecycle state is stopped and replicas are zero
- `not_applicable`: entity is destroyed
- `healthy`: binding resolved and Kubernetes readiness is satisfied

## Service Impact

Service status must include dependent App impact.

Example:

- Service instance health: `healthy`
- dependent impact: stopping affects `paperless`, `gitea`, and `immich`

Dependent impact is operational status, not health by itself.

## Backup Status

Backup status participates in aggregate status.

In Phase 1, backup status may be `unsupported`.

This is intentional.

Unsupported backup status is better than fake backup guarantees.
