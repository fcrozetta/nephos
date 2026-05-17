# Upgrade Policy

- Status: accepted
- Date: 2026-05-17
- Tags: upgrades, versions, apps, services, backups, phase-1

## Context and Problem Statement

Nephos must define how Apps, Services, catalogs, runtime packages, and Nephos itself are upgraded.

Upgrade behavior affects data safety, compatibility, rollback, and user trust.

Service upgrades are especially risky because Services often own persistent infrastructure state.

## Decision

Versions are pinned.

Pinned version categories include:

- Apps
- Services
- catalog entries
- Helm charts
- runtime deployment references
- Nephos itself

Do not use automatic `latest` behavior by default.

Upgrades are explicit and manual.

Apps and Services may have different upgrade strictness.

Service upgrades are higher risk than App upgrades.

Service upgrades are considered risky by default when persistent data exists.

Risky Service upgrades should require backup/checkpoint confirmation once the Service declares backup support.

Until backup support exists for a Service, Nephos must warn that no supported backup exists.

Rollback is best-effort in Phase 1, not guaranteed.

Compatibility checks are reserved but not deeply implemented in Phase 1.

## Consequences

Users must intentionally choose upgrades.

Nephos must track installed versions and desired versions.

Nephos must not silently move Apps or Services to newer catalog/chart versions.

Service packages should eventually declare upgrade behavior and backup requirements.

Phase 1 must be honest about limited rollback and backup support.

## Notes

Do not hide upgrade risk behind friendly UX.

Manual upgrades and pinned versions are the safer default for local-first self-hosted infrastructure.
