# Nephos Glossary

## App

A user-facing workload or product.

Examples:

- media systems
- source control platforms
- document management systems
- dashboards
- personal cloud applications
- AI applications

Apps may:

- expose routes/ingress
- persist data
- consume Services
- depend on capabilities
- be started/stopped independently
- be removed or destroyed

Apps are not shared infrastructure primitives.

## Service

A shared platform infrastructure component that exposes capabilities to Apps.

Examples:

- PostgreSQL
- Redis
- Object Storage
- Search engines
- Graph databases
- Queues
- SMTP
- Authentication providers
- AI inference backends

Services may:

- expose one or more capabilities
- provision app-scoped resources
- be shared by multiple Apps
- have dependency-aware lifecycle behavior

Do not call Services "plugins".

## Service Instance

An installed concrete Service.

A Service manifest defines an installable Service shape.

A Service instance is the installed platform/runtime instance of that Service.

Examples:

- `postgres-main`
- `redis-main`
- `neo4j-immich`

## Shared Service Instance

A Service instance intended to serve multiple Apps through separate bindings.

Shared Service instances are the default.

Where supported, a shared Service instance provisions app-scoped resources inside one runtime instance.

Example:

- one PostgreSQL Service instance with separate databases and users per App

## Dedicated Service Instance

A Service instance created because an App requests or requires isolation from a Service provider.

Dedicated Service instances are still first-class Services.

They may be explicitly bound by other Apps for integration.

Do not model dedicated Service instances as hidden App internals, embedded dependency containers, or Helm subcharts.

Use dedicated Service instance instead of app-private Service as the architecture term.

## Capability

A typed platform feature exposed by a Service and consumed by an App.

Examples:

- postgres
- sql
- redis
- s3
- graph-db
- document-db
- search
- kv
- smtp
- auth

Apps should depend on capabilities rather than concrete infrastructure whenever possible.

## Binding

A relationship between an App and a Service capability.

A binding represents how an App receives access to a capability.

Bindings are the source of dependent tracking between Apps and Service instances.

## Lifecycle State

The desired or historical lifecycle state of an entity.

Examples:

- installed
- running
- stopped
- disabled
- removed
- destroyed

Lifecycle state is separate from health status.

Removed and destroyed are lifecycle states, not health statuses.

## Health Status

An operational status that answers whether an entity that should be operating is operating correctly.

Accepted health status levels:

- `unknown`
- `pending`
- `healthy`
- `degraded`
- `blocked`
- `stopped`
- `not_applicable`

## Status Reason

An explanation for why an entity has a given health status.

Statuses must include reasons and/or evidence.

Do not expose opaque green/red status without explaining the cause.

## Nephos Manifest

A platform package definition for an App or Service.

Nephos manifests describe platform intent and relationships.

They are not Helm charts and are not raw Kubernetes manifests.

Nephos manifests may reference Helm charts or raw Kubernetes manifests as runtime deployment implementation details.

## App Manifest

A Nephos manifest that defines an installable App.

An App manifest focuses on user-facing workload concerns:

- required capabilities
- ingress or visibility intent
- storage intent
- config surface
- runtime deployment reference
- health/status expectations

## Service Manifest

A Nephos manifest that defines an installable Service.

A Service manifest focuses on shared infrastructure concerns:

- exposed capabilities
- supported binding types
- optional provisioning contracts
- optional Service operations
- backup/restore hooks or intent
- runtime deployment reference
- health/status expectations

## Runtime Deployment Reference

A reference from a Nephos manifest to the lower-level runtime deployment implementation.

Accepted Phase 1 deployment reference types:

- Helm chart
- raw Kubernetes manifests

Runtime deployment references are implementation details below the Nephos platform model.

## Service Operation

A typed backend/API-owned management action exposed by a Service.

Examples:

- provision app-scoped resource
- deprovision app-scoped resource
- rotate credentials
- backup
- restore
- run health diagnostic
- create database
- create bucket or prefix

Service management action is an acceptable descriptive phrase, but Service operation is the canonical term.

Do not model Service operations as arbitrary user-facing shell scripts.
