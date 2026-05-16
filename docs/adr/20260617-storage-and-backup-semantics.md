# Storage and Backup Semantics

- Status: draft
- Date: 2026-05-17
- Tags: storage, backups, pvc, data, lifecycle

## Context and Problem Statement

Storage is one of the highest-risk parts of Nephos.

Apps and Services may persist data.

Lifecycle commands must distinguish between stopping workloads, removing runtime objects, and destroying persistent data.

Backups may need to use Kubernetes primitives, service-native dumps, object storage syncs, or external storage targets.

## Current Understanding

Kubernetes owns storage primitives.

Nephos owns storage intent and policy.

Nephos-level storage concerns include:

- persistent data exists
- data should be preserved on stop
- data may be preserved on remove
- data must be deleted on destroy
- backup policy applies
- restore path exists

## Current Leaning

Start with Kubernetes PVCs and simple backup semantics.

Avoid promising advanced backup guarantees until implemented.

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
- remove vs destroy data behavior
- backup status visibility

## Status Notes

This is draft.

Do not treat storage deletion as a side effect of deleting Kubernetes runtime objects.

Data lifecycle must be explicit.
