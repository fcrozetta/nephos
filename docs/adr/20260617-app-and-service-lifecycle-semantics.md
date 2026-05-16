# App and Service Lifecycle Semantics

- Status: accepted
- Date: 2026-05-17
- Tags: lifecycle, apps, services, desired-state

## Context and Problem Statement

Words like stop, remove, delete, disable, and destroy are often used ambiguously.

Nephos needs precise lifecycle semantics because Apps and Services have different blast radius.

Apps are user-facing workloads.

Services are shared infrastructure primitives and may have dependents.

## Decision

Nephos lifecycle states and operations must distinguish:

- start
- stop
- disable
- remove
- destroy

Stopping is not removing.

Removing is not destroying.

## App Lifecycle Semantics

### stop

Stopping an App should:

- scale workloads to zero
- suspend scheduled jobs where applicable
- preserve data and metadata

Stopping should preserve:

- PVCs
- Secrets
- ConfigMaps
- bindings
- backups
- service relationships
- lifecycle metadata
- optionally ingress

### start

Starting an App restores its previous desired runtime state.

### disable

Disabling an App prevents automatic reconciliation or startup.

### remove

Removing an App removes deployed runtime objects while optionally preserving persistent data.

### destroy

Destroying an App deletes runtime objects and persistent data.

## Service Lifecycle Semantics

Services require dependency-aware lifecycle behavior.

Stopping or destroying a Service must check dependent Apps.

If dependent Apps exist, Nephos should warn and require explicit force.

## Rationale

Apps and Services are not symmetric.

Stopping an App is normally safe.

Stopping a shared Service can break dependent Apps.

## Consequences

Nephos must track dependencies between Apps, Services, capabilities, and bindings.

Nephos must preserve platform identity and relationships across stop/start operations.

## Future Direction

Nephos may later support sleep mode.

Sleep mode could scale workloads to zero, preserve state, preserve ingress or a wake endpoint, and restart workloads on demand.
