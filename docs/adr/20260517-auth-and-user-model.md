# Auth and User Model

- Status: accepted
- Date: 2026-05-17
- Tags: auth, users, local-first, phase-1, rbac

## Context and Problem Statement

Nephos is local-first and designed initially for user-owned infrastructure.

The project needs an initial auth and user model that supports the Phase 1 product without importing enterprise or multi-tenant complexity too early.

## Decision

Phase 1 is single-owner and local-first.

The CLI is a trusted local client.

No login, multi-user model, roles, or RBAC are required in Phase 1.

The Web UI is deferred for Phase 1.

When a Web UI is introduced, it should require local-owner auth, but not enterprise RBAC by default.

Friend, cloud, hosted, and multi-user scenarios are out of scope for Phase 1.

These scenarios are not forbidden forever.

## Consequences

Phase 1 can avoid designing user tenancy, organizations, role matrices, invitation flows, or hosted-account security.

The API and CLI should still avoid unsafe assumptions that would make future auth impossible.

Local CLI trust does not mean arbitrary unauthenticated network exposure is acceptable.

If the API is reachable beyond the local owner boundary, auth must be revisited before that becomes supported behavior.

## Notes

Do not design Phase 1 around enterprise IAM.

Do not use future multi-user possibilities as justification for complicating the local-first core.
