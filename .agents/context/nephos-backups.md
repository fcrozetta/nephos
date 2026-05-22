# Nephos Backups

## Core Decision

Nephos owns backup intent, policy, and status.

Services own or provide data-aware backup and restore implementations where data semantics matter.

Kubernetes owns storage primitives.

Kubernetes PVC snapshots or volume copies are not sufficient as a universal backup model for databases and graph stores.

## Phase 1 Scope

Phase 1 does not implement concrete backup/restore.

Phase 1 may document and track backup intent/status.

Phase 1 must not promise universal backup guarantees.

No first backup target is selected yet.

Local filesystem export/dump, NAS, object storage, cloud targets, PVC snapshots, and database-native dumps are deferred implementation decisions.

## Data Lifecycle

Stop preserves persistent data.

Remove removes runtime objects while preserving persistent data by default.

Destroy deletes runtime objects and persistent data.

Destroy must require destructive confirmation when persistent data exists.

There is no separate purge lifecycle operation.

## App Data

Apps should ideally not own durable data directly.

If an App saves durable data, that data should be represented through a Service or resource provider.

Local storage and host filesystem storage are resources, not invisible App internals.

## Backup Before Upgrade

Risky Service upgrades should require backup/checkpoint confirmation once the Service declares backup support.

Until backup support exists for a Service, Nephos must warn that no supported backup exists.

Service upgrades with persistent data are risky by default.

## Guardrails

Do not treat storage deletion as a side effect of deleting Kubernetes runtime objects.

Do not claim backup/restore guarantees until concrete implementations exist.

Do not treat PVC snapshots as universally correct backups for databases.
