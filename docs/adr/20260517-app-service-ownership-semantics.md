# App and Service Ownership Semantics

- Status: accepted
- Date: 2026-05-17
- Tags: apps, services, ownership, bindings, lifecycle

## Context and Problem Statement

Nephos separates Apps from Services.

Apps are user-facing workloads/products.

Services are shared infrastructure capability providers.

Nephos needs explicit ownership and sharing rules so dependencies do not collapse into hidden per-App containers, duplicated dependency lists, or raw Kubernetes/Helm composition.

## Decision

Use Service instance as the canonical term for an installed concrete Service.

Services are shared by default.

Phase 1 supports global/shared Service instances first.

Where a Service supports multiple app-scoped resources in one runtime instance, Nephos should use one shared Service instance by default.

Example:

- one PostgreSQL Service instance
- multiple app-scoped databases and users
- one binding per App requirement

An app-scoped resource is a Service-side resource created for a consuming App inside a Service instance.

App-scoped resources are created through typed provisioning.

They are not separate Apps, hidden Service instances, or embedded dependency containers.

Removing an App preserves app-scoped resources created for that App.

Destroying an App deletes app-scoped resources created for that App after destructive confirmation.

Apps may request isolation from a Service provider.

An App isolation request creates a dedicated Service instance when required by the Service or requested by the App.

Dedicated Service instances are still first-class Services.

Dedicated Service instances are not hidden App internals, embedded containers, or Helm subcharts.

Dedicated Service instances may be explicitly bound by other Apps when integration between Apps requires access to the same isolated provider.

Example:

- Neo4j Community does not support multiple databases in one instance.
- An App requiring Neo4j isolation may receive a dedicated Neo4j Service instance.
- Another App may explicitly bind to that same dedicated Service instance for integration.

Multiple Service instances of the same type and capability are allowed.

If exactly one eligible Service instance exposes a required capability, Nephos may auto-bind by default.

If multiple eligible Service instances expose a required capability and no default is configured, Nephos must require explicit selection.

Nephos may support a user-configurable default Service provider per capability.

Bindings are the source of dependent tracking.

Stopping, removing, or destroying a Service instance with dependents must require explicit force and show an impact list.

Shared Service instances are long-lived infrastructure by default.

## Decision Drivers

- Preserve Apps and Services as separate concepts.
- Preserve capability binding as the dependency model.
- Avoid recreating isolated Docker Compose stacks by default.
- Support Services that cannot multiplex app-scoped resources.
- Keep dependent tracking normalized and auditable.
- Protect shared infrastructure from accidental lifecycle operations.

## Consequences

Nephos must track bindings as first-class relationships.

Nephos should not maintain separate ad hoc dependent lists that can drift from bindings.

Service lifecycle operations must inspect bindings before stop, remove, or destroy.

Default provider selection becomes part of the platform state.

Dedicated Service instances need clear labels/metadata that record why they exist and whether other Apps may explicitly bind to them.

## Notes

Do not use "app-private Service" as the default architecture term.

The accepted concept is "dedicated Service instance" because the instance may be created for one App's isolation needs while still remaining explicitly shareable.
