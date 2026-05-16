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
