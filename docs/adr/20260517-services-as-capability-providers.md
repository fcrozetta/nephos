# Services as Capability Providers

- Status: accepted
- Date: 2026-05-17
- Tags: services, capabilities, bindings, domain-model

## Context and Problem Statement

Nephos Services are not just deployed infrastructure containers.

They need to expose typed capabilities that Apps can consume.

Without capabilities, Nephos becomes a deployment UI.

With capabilities, Nephos becomes a platform control plane.

## Decision

Services are capability providers.

Apps should declare capability requirements instead of depending directly on concrete infrastructure whenever possible.

## Rationale

A Service may expose one or more capabilities.

For example:

- PostgreSQL exposes postgres and sql
- Redis exposes redis and cache
- Object Storage exposes s3
- ArangoDB may expose graph-db, document-db, search, and kv
- Neo4j may expose graph-db
- SMTP exposes smtp

This lets Nephos resolve App requirements to installed Services.

## Consequences

Nephos needs a capability model.

Nephos needs a binding model connecting App requirements to Service capabilities.

Nephos can later support alternative providers for the same capability.

For example, a postgres capability could be fulfilled by:

- local PostgreSQL Service
- remote PostgreSQL instance
- managed PostgreSQL provider
- future replicated PostgreSQL Service

## Notes

The value of Nephos is not running containers.

The value is understanding and managing platform relationships.
