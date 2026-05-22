# Storage and Backup Semantics

- Status: accepted
- Date: 2026-05-17
- Tags: storage, backups, pvc, data, lifecycle

## Context and Problem Statement

Storage is one of the highest-risk parts of Nephos.

Apps should not own durable data directly where avoidable.

If an App saves durable data, that data should be represented through a Service or resource provider.

Local storage and host filesystem storage are resources, not invisible App internals.

Services may persist data and may provide storage or database capabilities to Apps.

Lifecycle commands must distinguish between stopping workloads, removing runtime objects, and destroying persistent data.

Backups may need to use Kubernetes primitives, service-native dumps, object storage syncs, or external storage targets.

## Decision

Kubernetes owns storage primitives.

Nephos owns storage intent and policy.

Nephos owns backup intent, policy, and status.

Services own or provide data-aware backup and restore implementations where data semantics matter.

Kubernetes PVC snapshots or volume copies are not sufficient as a universal backup model for databases and graph stores.

Phase 1 does not implement concrete backup/restore.

Phase 1 may document and track backup intent/status, but must not promise universal backup guarantees.

Stop preserves persistent data.

Remove removes runtime objects while preserving persistent data by default.

Destroy deletes runtime objects and persistent data.

Destroy must require destructive confirmation when persistent data exists.

There is no separate purge lifecycle operation unless a future ADR introduces it.

Risky Service upgrades should require backup/checkpoint confirmation once the Service declares backup support.

Until backup support exists for a Service, Nephos must warn that no supported backup exists.

## Nephos-Level Storage Concerns

Nephos-level storage concerns include:

- persistent data exists
- data should be preserved on stop
- data may be preserved on remove
- data must be deleted on destroy
- backup policy applies
- restore path exists

## Open Questions

Need to define:

- default storage class
- whether K3s local-path is acceptable initially
- Longhorn or similar later
- NAS backup integration
- PVC snapshot support
- database-native backup behavior
- object storage backup behavior
- restore workflow
- retention policy
- backup status visibility
- first concrete backup implementation
- Service-native backup contract
- local filesystem export/dump format
- backup-before-upgrade flow

## Status Notes

This decision is accepted.

Do not treat storage deletion as a side effect of deleting Kubernetes runtime objects.

Data lifecycle must be explicit.

No concrete backup implementation is approved for Phase 1.
