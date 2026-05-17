# Phase 1 Scope

- Status: accepted
- Date: 2026-05-17
- Tags: phase-1, scope, k3s, cli, catalog, lifecycle

## Context and Problem Statement

Nephos needs a tight Phase 1 boundary.

The first phase should prove the platform model without expanding into Web UI, HA, backup implementation, service mesh, or enterprise concerns.

## Decision

Phase 1 targets single-node K3s.

K3s is the default real runtime backend.

Cluster lifecycle support is minimal.

The CLI may expose cluster commands, but Phase 1 does not need a fully polished cluster lifecycle manager.

The backend API is the control-plane owner.

The separate CLI repository talks to the backend API/local controller.

Phase 1 includes:

- Nephos backend API
- SQLite desired-state database
- simple explicit SQL migrations
- in-process API-owned reconciler
- separate Python/Typer CLI
- local filesystem catalog
- separate App and Service Nephos manifests
- Helm-primary runtime deployment
- raw Kubernetes manifest fallback
- raw Kubernetes manifest fallback shape deferred until first needed
- App and Service model
- Service instances
- capabilities
- bindings
- basic provider selection
- shared/global Service instances first
- basic ingress intent
- minimal Nephos-aware health/status
- backup intent/status only
- pinned versions and manual upgrades
- Phase 1 App config option types `string`, `integer`, `boolean`, and `enum`
- `secret` App config option type deferred
- unknown manifest fields rejected once canonical schemas exist

Phase 1 lifecycle commands for Apps and Services:

- install
- start
- stop
- remove
- destroy

`disable` is deferred.

Phase 1 supports local filesystem catalog loading from day one.

The repo should ship a tiny reference catalog rather than hardcoding App behavior in backend logic.

The canonical reference scenario is:

- Paperless App
- PostgreSQL Service

Multi-component Apps are allowed conceptually.

Internal App components communicate through normal Kubernetes Services/networking.

No service mesh is required or included.

## Non-Goals

Phase 1 does not include:

- Web UI
- service mesh
- HA
- autoscaling
- resource profiles
- concrete backup/restore implementation
- enterprise IAM/RBAC
- CRD-first source of truth
- GitOps source of truth
- remote/signed catalogs
- OCI catalog distribution
- dedicated Service instance implementation
- Service operation implementation
- full cluster lifecycle management polish

## Consequences

Phase 1 remains narrow enough to validate the core model:

Apps + Services + capabilities + bindings + lifecycle + reconciliation.

Users may expect backup/restore, Web UI, remote catalogs, and more complete cluster lifecycle earlier than Phase 1 provides.

That is acceptable.

The platform model must be correct before broad UX and operations features are added.

## Notes

Do not implement Paperless or PostgreSQL as hardcoded backend cases.

Use the local filesystem catalog and manifest path, even if the reference catalog is tiny.
