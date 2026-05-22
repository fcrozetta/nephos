# Nephos Service Ownership

## Core Decision

Installed concrete Services are Service instances.

Services are shared by default.

Shared infrastructure is expected to be long-lived.

Apps consume Service instances through bindings.

Bindings are the source of dependent tracking.

## Service Instance

A Service instance is an installed concrete Service.

Examples:

- `postgres-main`
- `redis-main`
- `neo4j-immich`
- `svc-arangodb`

A Service manifest defines an installable Service shape.

A Service instance is the installed runtime and platform-state instance of that Service.

## Shared Service Instance

A shared Service instance is the default Service instance mode.

It may serve multiple Apps through separate bindings.

When supported by the Service, Nephos should provision app-scoped resources inside one shared instance.

Examples:

- PostgreSQL instance with one database/user per App
- Object storage Service with one bucket or prefix per App
- Redis instance with app-specific credentials, logical databases, or prefixes where appropriate

## App-Scoped Resource

An app-scoped resource is a Service-side resource created for a consuming App inside a Service instance.

Examples:

- PostgreSQL database and user
- object storage bucket or prefix
- Redis logical database, prefix, or credential scope where supported

App-scoped resources are created through a typed provisioning contract.

They are not separate Apps.

They are not hidden Service instances.

Phase 1 recognizes `app-scoped-resource` and `none` as provisioning modes.

Remove preserves app-scoped resources created for an App.

Destroy deletes app-scoped resources created for an App after destructive confirmation.

## Dedicated Service Instance

A dedicated Service instance exists because an App requested or required isolation from a Service provider.

Dedicated Service instances are still first-class Services.

They are not hidden App internals.

They are not embedded dependency containers.

They are not Helm subcharts owned only by an App.

Other Apps may explicitly bind to a dedicated Service instance when integration between Apps requires access to the same provider.

Example:

- Neo4j Community does not support multiple databases in one runtime instance.
- An App requiring Neo4j can request a dedicated Neo4j Service instance.
- Another App may explicitly bind to that same Neo4j Service instance for integration.

Use dedicated Service instance instead of app-private Service as the architecture term.

## Provider Selection

Multiple Service instances may expose the same capability.

If exactly one eligible Service instance exposes a required capability, Nephos may auto-bind by default.

If multiple eligible Service instances expose a required capability and no default provider is configured, Nephos must require explicit selection.

Nephos may support a user-configurable default provider per capability.

Example:

- `postgres-main` is the default `postgres` provider.
- `postgres-lab` exists but is not default.
- Apps requiring `postgres` bind to `postgres-main` unless they explicitly choose another provider.

## Dependent Tracking

Bindings are the source of dependent tracking.

Do not maintain a separate ad hoc `used_by` list as authoritative state.

Given a binding:

- App: `paperless`
- requirement: `postgres`
- Service instance: `postgres-main`
- capability: `postgres`

Nephos knows:

- `paperless` depends on `postgres-main`
- `postgres-main` has `paperless` as a dependent
- stopping `postgres-main` impacts `paperless`
- removing `paperless` removes or updates the binding

## Lifecycle Implications

Stopping, removing, or destroying a Service instance with dependents must:

- detect dependent Apps through bindings
- show an impact list
- require explicit force

Destroying a Service instance must also follow explicit data deletion semantics.

Do not treat Service instance deletion as a raw Kubernetes delete side effect.

## Phase 1 Scope

Phase 1 should support shared/global Service instances first.

Dedicated Service instances are reserved as a concept for Phase 1 unless implementation scope explicitly includes them later.

The model must not block future dedicated Service instances.
