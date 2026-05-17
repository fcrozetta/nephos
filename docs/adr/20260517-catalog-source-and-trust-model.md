# Catalog Source and Trust Model

- Status: accepted
- Date: 2026-05-17
- Tags: catalog, trust, manifests, phase-1

## Context and Problem Statement

Nephos needs a catalog model for discovering installable Apps and Services.

The catalog must reinforce the Nephos platform model:

- Apps
- Services
- capabilities
- bindings
- lifecycle semantics
- dependency awareness

The catalog must not become a generic app marketplace detached from composition.

## Decision

Phase 1 uses local filesystem catalogs.

Supported Phase 1 catalog sources:

- repo-shipped reference catalog entries
- user-configured local filesystem catalog paths

Nephos must not hardcode App or Service behavior in backend logic.

Even the reference scenario should exercise the catalog and manifest path.

User-created local catalog entries are allowed in Phase 1.

Until the manifest schema is accepted, local user-created entries do not carry a schema stability promise.

## Trust Model

Phase 1 treats local catalog files as trusted local-owner input.

This matches the accepted single-owner/local-first model.

Phase 1 does not provide:

- catalog signing
- remote catalog verification
- package sandboxing guarantees
- trust policy for third-party remote catalogs
- private remote catalog credentials

Local trust does not mean Nephos should execute arbitrary shell snippets from catalogs as product behavior.

Service operations and runtime deployment mechanisms still need typed, backend-owned contracts.

## Catalog Metadata

For Phase 1, App and Service manifests carry the minimal catalog metadata needed to list and select entries.

A separate catalog index is deferred.

The manifest should remain the package boundary.

Catalog metadata should not become a second source of truth for package semantics.

## Deferred Sources

Deferred catalog sources:

- Git repositories
- OCI artifacts or registries
- remote indexes
- signed catalogs
- private remote catalogs

These need future trust, versioning, update, and credential decisions.

## Consequences

Local filesystem catalogs keep Phase 1 simple and aligned with local-first infrastructure ownership.

Supporting user-created local catalog entries early lets the platform model be tested without waiting for remote distribution.

Deferring signing and remote trust prevents premature security theater.

The downside is that Phase 1 catalog sharing is manual and local.

Remote catalog UX, private catalogs, and signed distribution remain unresolved future work.

## Notes

Do not introduce remote catalog fetching, signing, or OCI distribution without a new decision.

Do not create schema files under `schemas/` until Fer approves the concrete manifest field schema.
