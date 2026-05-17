# Nephos Catalog

## Purpose

The catalog exists to support platform composition.

It is not merely an app marketplace.

Catalog entries must reinforce:

- Apps
- Services
- capabilities
- bindings
- lifecycle semantics
- dependency awareness

## Phase 1 Sources

Phase 1 uses local filesystem catalogs.

Supported Phase 1 sources:

- repo-shipped reference catalog entries
- user-configured local filesystem catalog paths

The repo may ship a tiny reference catalog.

The backend must not hardcode App or Service behavior.

Reference scenarios should exercise the catalog and manifest path.

## User-Created Entries

User-created local catalog entries are allowed in Phase 1.

Until the manifest schema is accepted, local user-created entries do not carry a schema stability promise.

Do not create schema files under `schemas/` until Fer approves the manifest shape.

Do not create examples under `examples/` until the example shape is approved.

## Trust Model

Phase 1 treats local catalog files as trusted local-owner input.

There is no Phase 1 support for:

- catalog signing
- remote catalog verification
- package sandboxing guarantees
- third-party remote catalog trust policy
- private remote catalog credentials

Local trust does not allow arbitrary catalog shell scripts to become a product feature.

Runtime deployment and Service operations must still flow through Nephos-owned typed contracts.

## Metadata Model

For Phase 1, App and Service manifests carry minimal catalog metadata.

A separate catalog index is deferred.

Catalog metadata must not become a second source of truth for package semantics.

The Nephos manifest remains the package boundary.

## Deferred Sources

Deferred catalog sources:

- Git repositories
- OCI artifacts or registries
- remote indexes
- signed catalogs
- private remote catalogs

Future remote catalogs need explicit decisions for:

- trust model
- signing and verification
- credentials
- versioning
- update behavior
- compatibility metadata
