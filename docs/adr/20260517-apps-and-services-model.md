# Apps and Services Model

- Status: accepted
- Date: 2026-05-17
- Tags: domain-model, apps, services, capabilities

## Context and Problem Statement

Nephos needs a domain model for installable and manageable things.

The previous term "plugin" is not appropriate for shared infrastructure resources.

A plugin sounds like an extension attached to an application.

Nephos needs to model both user-facing workloads and shared infrastructure capabilities.

## Decision

Nephos has two primary top-level installable concepts:

- Apps
- Services

Apps are user-facing workloads or products.

Services are shared platform infrastructure components that expose capabilities.

## Rationale

This split reflects the product model clearly.

Apps consume Services.

Services expose capabilities.

This lets Nephos model platform relationships rather than just deployed containers.

## Examples

Apps:

- media systems
- source control platforms
- document management systems
- dashboards
- personal cloud applications
- AI applications

Services:

- PostgreSQL
- Redis
- Object Storage
- Search engines
- Graph databases
- Queues
- SMTP
- Authentication providers
- AI inference backends

## Consequences

Nephos should not call shared infrastructure "plugins".

Nephos should not treat infrastructure databases as random Apps.

Unsupported databases such as ArangoDB, Neo4j, and ArcadeDB should be modeled as Services exposing capabilities.

## Notes

The core abstraction is:

Apps consume capabilities exposed by Services.
