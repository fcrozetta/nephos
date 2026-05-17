# Nephos Phase 1

## Accepted Scope So Far

Phase 1 is local-first and single-owner.

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
- Kubernetes runtime substrate
- no CRD-first model
- no GitOps source-of-truth model

State:

- Nephos API/database is canonical desired state
- YAML is import/export only

Catalog and packaging:

- separate App and Service Nephos manifests
- Helm-primary runtime deployment underneath manifests
- raw Kubernetes manifest fallback
- local filesystem catalog first
- no schema files until Fer approves shape

Services:

- shared/global Service instances first
- dedicated Service instances reserved as concept
- Service operations optional and contract deferred

Resource/auth:

- no Nephos resource policy system
- running replicas `1`
- stopped/disabled replicas `0`
- no HA/autoscaling/affinity/quotas
- single-owner local auth model
- no Phase 1 login/RBAC
- Web UI deferred

## Still To Define

- exact Phase 1 App/Service command subset
- exact binding behavior for first reference scenario
- namespace strategy details
- ingress/TLS/local DNS behavior
- secrets naming and preservation behavior
- backup guarantees
- health/status model
- upgrade behavior
- local development workflow
- packaging/distribution
- reference scenario
