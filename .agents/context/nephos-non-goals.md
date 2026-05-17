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
- service mesh
- CRD-first source of truth
- GitOps source of truth
- remote catalog trust/signing
- remote catalog fetching
- OCI catalog distribution
- separate catalog index
- default-deny NetworkPolicy
- Cloudflare Tunnel automation
- Tailscale automation
- DNS automation
- TLS/cert-manager automation
- external secret manager integration
- automatic latest upgrades
- guaranteed rollback
- concrete backup/restore implementation
- dedicated Service instance implementation
- Service operation implementation
- `disable` lifecycle operation
- full cluster lifecycle management polish

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

## Runtime Boundary Non-Goals

Phase 1 does not automate public exposure.

Manually configured tunnels such as Cloudflare Tunnel must be compatible with Nephos local ingress, but Nephos does not manage tunnel credentials, tunnel lifecycle, or DNS records in Phase 1.

Phase 1 does not provide advanced secret management, rotation, or external vault integration.

## Catalog Non-Goals

Phase 1 does not provide remote catalog distribution, catalog signing, third-party catalog trust policy, or private remote catalog credentials.

Phase 1 does not provide sandboxing guarantees for catalog-provided packages.
