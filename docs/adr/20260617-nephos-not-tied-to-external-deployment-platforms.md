# Nephos Is Not Tied to External Deployment Platforms

- Status: accepted
- Date: 2026-05-17
- Tags: strategy, runtime, coolify, independence

## Context and Problem Statement

External deployment platforms can provide useful runtime management, UI, deployment, logs, domains, and database features.

However, Nephos is being designed as a platform control plane with its own Apps, Services, capabilities, bindings, and lifecycle semantics.

Tying Nephos directly to an external deployment platform would constrain the domain model.

## Decision

Nephos will not depend on any external deployment platform as a foundational requirement.

Nephos should own its platform model and use Kubernetes/K3s directly as its primary runtime substrate.

## Rationale

External deployment platforms are useful but opinionated.

Nephos needs to preserve:

- architectural independence
- portability
- control over platform semantics
- capability binding
- Service provisioning contracts
- dependency-aware lifecycle behavior

## Consequences

Nephos should not be implemented as a wrapper around an external deployment platform.

External deployment integrations may be explored later only as optional adapters if useful.

K3s remains the primary runtime substrate.

## Notes

The differentiator is composable self-hosted infrastructure through Apps, Services, capabilities, bindings, and platform-level relationships.
