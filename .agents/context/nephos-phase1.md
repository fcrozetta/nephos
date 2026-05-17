# Nephos Phase 1

## Accepted Scope So Far

Phase 1 is local-first and single-owner.

Phase 1 targets single-node K3s.

Backend/control plane:

- `nephos` repository
- Python
- FastAPI
- SQLite canonical desired-state database
- simple explicit SQL migrations
- official Python Kubernetes client
- API-owned in-process reconciler

CLI:

- separate `nephos-cli` repository
- Python
- Typer
- trusted local client
- talks to Nephos API/local controller

Runtime:

- K3s default real backend
- single-node K3s target
- Kubernetes runtime substrate
- minimal cluster lifecycle support
- no CRD-first model
- no GitOps source-of-truth model

State:

- Nephos API/database is canonical desired state
- YAML is import/export only

Catalog and packaging:

- separate App and Service Nephos manifests
- Helm-primary runtime deployment underneath manifests
- raw Kubernetes manifest fallback
- local filesystem catalog from day one
- tiny repo-shipped reference catalog
- no schema files until Fer approves shape

Services:

- shared/global Service instances first
- dedicated Service instances reserved as concept
- Service operations optional and contract deferred

Apps:

- multi-component Apps are allowed conceptually
- internal App component communication uses normal Kubernetes Services/networking
- no service mesh

Lifecycle:

- App and Service `install`
- App and Service `start`
- App and Service `stop`
- App and Service `remove`
- App and Service `destroy`
- `disable` deferred

Upgrades/backups:

- pinned versions
- explicit/manual upgrades
- no automatic latest
- Service upgrades with persistent data are risky by default
- rollback best-effort, not guaranteed
- no concrete backup/restore implementation
- backup intent/status may be tracked
- destroy requires destructive confirmation when persistent data exists

Health/status:

- Nephos-aware aggregate status
- desired lifecycle state
- reconciliation state
- Kubernetes object existence/readiness
- binding resolved/unresolved
- dependency availability
- route known/unknown
- backup status as `unsupported`
- Service dependent impact
- status reasons/evidence required

Resource/auth:

- no Nephos resource policy system
- running replicas `1`
- stopped/disabled replicas `0`
- no HA/autoscaling/affinity/quotas
- single-owner local auth model
- no Phase 1 login/RBAC
- Web UI deferred

Reference scenario:

- Paperless App
- PostgreSQL Service
- reference catalog should exercise local filesystem catalog/manifest flow

## Still To Define

- exact binding behavior for first reference scenario
- namespace strategy details
- ingress/TLS/local DNS behavior
- secrets naming and preservation behavior
- backup guarantees
- local development workflow
- packaging/distribution
- reference scenario exact command flow
