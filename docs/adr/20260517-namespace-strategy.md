# Namespace Strategy

- Status: draft
- Date: 2026-05-17
- Tags: kubernetes, namespaces, isolation, runtime

## Context and Problem Statement

Nephos needs a Kubernetes namespace strategy for Apps, Services, and control-plane components.

Namespaces affect isolation, lifecycle operations, debugging, resource ownership, and cleanup behavior.

## Current Leaning

Use:

- one namespace per App
- one namespace per Service
- reserved nephos-system namespace for Nephos control plane

Example:

- nephos-system
- app-paperless
- app-immich
- svc-postgres
- svc-redis
- svc-arangodb

## Rationale

Separate namespaces make ownership and lifecycle boundaries clearer.

App lifecycle operations should not accidentally affect shared Services.

Service lifecycle operations require dependency awareness.

## Open Questions

Need to decide:

- namespace naming rules
- whether namespaces are preserved on remove
- whether destroy deletes namespaces
- how shared secrets are handled
- whether network policies are default-deny
- how cross-namespace service discovery should work

## Status Notes

This is draft.

Do not place all Apps and Services into a single namespace without revisiting this decision.
