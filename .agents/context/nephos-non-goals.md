# Nephos Non-Goals

## Product Non-Goals

Nephos is not:

- a generic container dashboard
- a raw Kubernetes dashboard
- a thin kubectl wrapper
- an app marketplace without composition
- a Kubernetes replacement
- a custom scheduler
- a custom networking stack
- a custom storage engine
- a custom ingress controller
- a custom container runtime
- a service mesh

## Phase 1 Non-Goals

Phase 1 does not include:

- HA
- autoscaling
- resource quotas
- affinity or anti-affinity
- scheduler policy
- multi-node production scheduling guarantees
- multi-cluster support
- multi-region federation
- enterprise IAM
- roles/RBAC
- user accounts
- friend/cloud/hosted multi-user scenarios
- Web UI
- CRD-first source of truth
- GitOps source of truth
- remote catalog trust/signing
- OCI catalog distribution
- automatic latest upgrades
- guaranteed rollback
- concrete backup/restore implementation

## Resource Non-Goals

Phase 1 does not provide production-grade resource isolation.

Phase 1 does not define Nephos resource profiles.

Phase 1 does not expose raw Kubernetes CPU/memory knobs as the primary UX.

## Auth Non-Goals

Phase 1 does not design for enterprise IAM or SaaS tenancy.

Future multi-user or hosted scenarios are not forbidden, but they are not the Phase 1 design center.

## Backup And Upgrade Non-Goals

Phase 1 does not provide universal backup/restore.

Phase 1 does not guarantee rollback.

Phase 1 does not automatically upgrade Apps, Services, charts, catalogs, or Nephos.
