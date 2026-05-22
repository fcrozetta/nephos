# Reference Scenario

- Status: accepted
- Date: 2026-05-17
- Tags: reference-scenario, paperless, postgres, phase-1

## Context and Problem Statement

Nephos needs one canonical end-to-end scenario that exercises the core platform model without turning the backend into hardcoded app logic.

The reference scenario should validate:

- local filesystem catalog loading
- App and Service manifests
- Service capability exposure
- App capability requirements
- binding
- ingress intent
- lifecycle semantics
- dependency-aware Service operations
- data preservation and deletion semantics

## Decision

Use Paperless plus PostgreSQL as the canonical Phase 1 reference scenario.

The reference scenario contains:

- PostgreSQL Service
- Paperless App
- `postgres` capability
- Paperless binding to PostgreSQL
- local route intent using generated hosts such as `paperless.nephos.local` and `paperless.nephos.fcrozetta.app`

Root domain API resources use `/platform/config/domains`.

The exact CLI command spelling for root domain operations remains open.

Paperless requires only PostgreSQL in the Phase 1 reference scenario.

Do not include Redis, object storage, S3, or additional Services in the canonical Phase 1 scenario unless a later decision expands it.

## Canonical Flow

The canonical flow is:

1. Install PostgreSQL Service from a local filesystem catalog entry.
2. Install Paperless App from a local filesystem catalog entry.
3. Bind Paperless to the `postgres` capability exposed by PostgreSQL.
4. PostgreSQL provisions an app-scoped database/user for Paperless.
5. Nephos materializes PostgreSQL binding outputs into the Paperless App namespace.
6. Expose Paperless through local ingress intent.
7. Start Paperless.
8. Verify Paperless has a known route and binding status.
9. Verify the binding exposes PostgreSQL logical fields `host`, `port`, `database`, `username`, `password`, and `uri`.
10. Stop Paperless.
11. Start Paperless again.
12. Verify Paperless data is preserved across stop/start.
13. Attempt to stop PostgreSQL while Paperless depends on it.
14. Nephos blocks the Service stop unless forced and shows an impact list.
15. Remove Paperless while preserving persistent data and metadata.
16. Verify remove preserves the app-scoped PostgreSQL resource and binding metadata.
17. Destroy Paperless with destructive confirmation, deleting persistent data and app-scoped PostgreSQL resources associated with Paperless.

Command spelling and status output are not finalized yet.

The flow should eventually be represented with concrete CLI commands after the CLI command contract is accepted.

## Catalog And Manifest Rules

The reference scenario must use the local filesystem catalog and Nephos manifest path.

Do not hardcode Paperless or PostgreSQL behavior in backend logic.

Do not create canonical files under `examples/` until manifest validation plus command/status shape are stable enough and Fer approves promotion.

Draft manifest sketches may live under `.agents/drafts/manifests/` while schema design is in progress.

Draft manifests are non-canonical and must not be treated as source of truth.

## Ingress Rule

Use illustrative generated hosts such as:

- `paperless.nephos.local`
- `paperless.nephos.fcrozetta.app`

These are two configured root domains for the same Paperless route.

One configured root domain is canonical/default.

The other generated hostnames are aliases.

The ingress root domains are platform desired state created during Nephos setup before Apps are installed.

The setup UX and command implementation are deferred to `nephos-cli` after Nephos API `0.0.1`.

DNS, Cloudflare Tunnel, and TLS termination remain user-managed in Phase 1.

The route should exercise Nephos-owned route intent and Kubernetes-owned Ingress resources.

## Service Dependency Impact

The reference scenario must include Service dependency impact.

Stopping PostgreSQL while Paperless depends on it should be blocked unless the user explicitly forces the operation.

The blocked operation must show an impact list explaining that Paperless depends on PostgreSQL through a binding.

## Consequences

The reference scenario exercises the platform differentiator:

Apps consume capabilities exposed by Services through bindings.

It keeps Phase 1 focused while still covering lifecycle, ingress, status, and data semantics.

Paperless is a heavier reference App than a trivial demo app, but it better represents real self-hosted infrastructure.

## Notes

Do not implement Paperless or PostgreSQL as special backend cases.

Do not use this ADR to infer concrete manifest schemas.
