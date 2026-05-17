# Nephos Open Questions

## Namespace Strategy

Question:

What namespace model should Nephos use?

Current leaning:

- one namespace per App
- one namespace per Service
- reserved nephos-system namespace for Nephos control plane

## Manifest Schema Details

Question:

What are the concrete App and Service manifest schemas?

Accepted direction:

- separate App and Service Nephos manifest formats
- Helm-primary runtime deployment references
- raw Kubernetes manifest fallback
- no schema file until Fer approves the shape

Need to decide:

- exact field names
- manifest filenames
- versioning scheme
- required vs optional fields
- config surface format
- capability requirement syntax
- exposed capability syntax
- runtime deployment reference syntax
- validation rules

## Dedicated Service Sharing Policy Details

Question:

How should explicit sharing of dedicated Service instances work?

Accepted direction:

- dedicated Service instances are created because an App requests or requires isolation
- dedicated Service instances remain first-class Services
- other Apps may explicitly bind to a dedicated Service instance for integration
- Phase 1 reserves the concept and supports shared/global Service instances first

Need to decide:

- whether a dedicated Service instance has an owning/initiating App field
- whether explicit sharing requires owner confirmation
- whether dedicated instances advertise capabilities normally or behind a sharing flag
- whether default provider selection may choose a dedicated instance
- how backup/restore lifecycle works when several Apps bind to a dedicated instance
- how destroy impact lists represent initiating App vs later dependents

## Service Operation Contract

Question:

What is the concrete contract for Service operations?

Accepted direction:

- Service operation is the canonical term
- Service management action is only a descriptive phrase
- Service operations are optional in Phase 1
- Service operations must be backend/API-owned and typed
- Service operations must not be arbitrary user-facing shell scripts

Need to decide:

- operation declaration format
- input/output schema
- execution model
- audit/status model
- permissions and safety prompts
- idempotency expectations
- relationship to binding lifecycle
- relationship to backup/restore lifecycle

## Catalog Source and Trust Beyond Phase 1

Question:

How should non-local catalogs work after Phase 1?

Accepted Phase 1 direction:

- local filesystem catalog first

Deferred:

- Git repositories
- OCI artifacts or registries
- remote indexes
- signed catalogs
- private remote catalogs

Need to decide:

- trust model
- signing/verifying catalog entries
- private catalog credentials
- catalog versioning
- catalog update behavior
- how catalog metadata relates to package manifests

## Backend and CLI Packaging

Question:

How should the backend and CLI be packaged and distributed?

Current accepted repository boundary:

- backend/control plane lives in `nephos`
- CLI lives in `../nephos-cli`

Need to decide:

- backend package layout
- backend container image strategy
- CLI installation path
- version compatibility between backend and CLI
- release process across the two repositories

## Future Resource Profile Design

Question:

How should Nephos model resource profiles after Phase 1?

Accepted Phase 1 direction:

- no Nephos resource policy system
- replicas are `1` when running and `0` when stopped/disabled
- resource profiles are reserved but not defined
- raw Kubernetes CPU/memory knobs are not primary UX
- no HA/autoscaling/affinity/quotas

Need to decide later:

- profile names and semantics
- CPU/memory request and limit mapping
- Service-specific defaults
- App-specific defaults
- capacity warnings
- override model
- validation behavior

## Future Auth and RBAC Model

Question:

What auth model is needed after Phase 1?

Accepted Phase 1 direction:

- single-owner local-first
- trusted local CLI
- Web UI deferred
- no login/RBAC in Phase 1
- friend/cloud/multi-user scenarios are Phase 1 non-goals

Need to decide later:

- local-owner Web UI auth
- API bind/listen policy
- token model
- remote access model
- whether multi-user is ever needed
- whether roles/RBAC are needed

## Concrete Backup Implementation Design

Question:

What concrete backup/restore implementations should Nephos support after Phase 1?

Accepted Phase 1 direction:

- no concrete backup/restore implementation
- Nephos owns backup intent/policy/status
- Services own or provide data-aware implementations
- PVC snapshots are not universally sufficient for databases
- destroy requires destructive confirmation when persistent data exists

Need to decide later:

- first backup target
- database-native dump strategy
- object storage backup strategy
- PVC snapshot support
- filesystem/local storage backup strategy
- retention policy
- restore workflow
- backup status model
- backup-before-upgrade flow

## Upgrade Compatibility Design

Question:

How should Nephos validate upgrade compatibility after Phase 1?

Accepted Phase 1 direction:

- versions are pinned
- upgrades are explicit/manual
- no automatic latest
- Service upgrades with persistent data are risky by default
- rollback is best-effort, not guaranteed

Need to decide later:

- catalog compatibility metadata
- App/Service version constraints
- Service capability compatibility
- chart version compatibility
- preflight checks
- rollback metadata
- backup/checkpoint requirements

## Health And Status Check Implementation Details

Question:

How should Nephos implement concrete health/status checks after the Phase 1 minimum?

Accepted Phase 1 direction:

- Nephos-aware aggregate status
- Kubernetes readiness is an input, not the whole model
- lifecycle state is separate from health status
- removed/destroyed are lifecycle states
- backup status participates as `unsupported`
- status reasons/evidence are required

Need to decide later:

- exact status API shape
- status event/history model
- app-specific probe support
- Service-specific diagnostic support
- route reachability checks
- storage health checks
- backup status transitions
- how status affects exit codes in CLI
- how status renders in future Web UI

## Reference Scenario Exact Flow

Question:

What exact command flow and manifest examples should define the Paperless + PostgreSQL reference scenario?

Accepted direction:

- Paperless App
- PostgreSQL Service
- local filesystem catalog
- Nephos manifests
- capability binding
- basic ingress intent
- lifecycle install/start/stop/remove/destroy
- data preserved on stop/remove
- destroy requires destructive confirmation when persistent data exists

Need to decide:

- exact catalog directory layout
- exact manifest filenames
- exact App manifest fields
- exact Service manifest fields
- exact commands
- expected status outputs
- namespace names
- secret names
- ingress hostname policy
- data preservation checks

## Local Development Workflow

Question:

What is the canonical local development workflow for Nephos?

Need to decide:

- whether local backend development uses `uv`
- how SQLite state is initialized/reset
- how K3s is started for local development
- whether Docker Compose is used for supporting developer services
- how `../nephos-cli` points to a local backend

## Testing Approach

Question:

What is the required testing baseline before implementation starts?

Current default from Fer's ecosystem:

- pytest
- Ruff
- uv

Need to decide:

- unit vs integration test boundaries
- whether Kubernetes integration tests use K3s, kind, or mocks
- whether CLI tests live only in `../nephos-cli`
