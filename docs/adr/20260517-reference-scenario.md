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
- local route intent using a placeholder host such as `paperless.<local-domain>`

The exact local domain remains open.

Paperless requires only PostgreSQL in the Phase 1 reference scenario.

Do not include Redis, object storage, S3, or additional Services in the canonical Phase 1 scenario unless a later decision expands it.

## Canonical Flow

The canonical flow is:

1. Install PostgreSQL Service from a local filesystem catalog entry.
2. Install Paperless App from a local filesystem catalog entry.
3. Bind Paperless to the `postgres` capability exposed by PostgreSQL.
4. Expose Paperless through local ingress intent.
5. Start Paperless.
6. Verify Paperless has a known route and binding status.
7. Stop Paperless.
8. Start Paperless again.
9. Verify Paperless data is preserved across stop/start.
10. Attempt to stop PostgreSQL while Paperless depends on it.
11. Nephos blocks the Service stop unless forced and shows an impact list.
12. Remove Paperless while preserving persistent data and metadata.
13. Destroy Paperless with destructive confirmation, deleting App-owned persistent data.

Command spelling and status output are not finalized yet.

The flow should eventually be represented with concrete CLI commands after the CLI command contract is accepted.

## Catalog And Manifest Rules

The reference scenario must use the local filesystem catalog and Nephos manifest path.

Do not hardcode Paperless or PostgreSQL behavior in backend logic.

Do not create canonical files under `examples/` until Fer approves the manifest/example shape.

Draft manifest sketches may live under `.agents/drafts/manifests/` while schema design is in progress.

Draft manifests are non-canonical and must not be treated as source of truth.

## Ingress Rule

Use an illustrative local route such as:

- `paperless.<local-domain>`

The exact local domain, wildcard behavior, DNS behavior, and TLS behavior remain open.

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
