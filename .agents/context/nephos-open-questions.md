# Nephos Open Questions

## Namespace Details

Question:

What exact namespace naming and metadata rules should Nephos use?

Accepted direction:

- one namespace per App instance
- one namespace per Service instance
- `nephos-system` for Nephos control-plane/runtime support components
- `app-<slug>` naming for Apps
- `svc-<slug>` naming for Services
- remove preserves namespaces
- destroy deletes namespaces by default after destructive confirmation when persistent data exists
- no default-deny NetworkPolicy in Phase 1

Need to decide:

- slug normalization
- collision handling
- required labels and annotations
- future NetworkPolicy model
- exact cross-namespace connection metadata in bindings

## Local Ingress And Exposure Details

Question:

What exact local hostname, wildcard domain, DNS, and TLS strategy should Nephos use?

Accepted direction:

- Traefik default for Phase 1 because K3s includes it
- Nephos owns route/visibility intent
- Kubernetes owns Ingress resources
- Phase 1 implements local visibility
- private, public, and tailnet visibility are reserved
- Cloudflare Tunnel and Tailscale automation are deferred
- manually configured Cloudflare Tunnel must work with Nephos local ingress
- stopped Apps keep route intent and may keep runtime ingress
- remove/destroy remove runtime ingress

Need to decide:

- default local domain
- wildcard hostname policy
- route collision behavior
- TLS/cert-manager strategy
- whether Services can expose admin routes
- future Cloudflare adapter shape
- future Tailscale adapter shape

## Secrets Details

Question:

What exact secret naming, labeling, rotation, and backup behavior should Nephos use?

Accepted direction:

- Kubernetes Secrets in Phase 1
- external secret managers deferred
- future secret managers may be modeled as Services
- Service-internal/admin secrets live in Service namespaces
- App binding credentials are materialized into App namespaces
- Apps should not read Service namespace Secrets directly
- stop/remove preserve Secrets
- destroy deletes Secrets for the destroyed entity
- secret values are redacted by default

Need to decide:

- exact secret naming convention
- exact labels/annotations
- rotation behavior
- whether/how secrets are included in Nephos state backup
- future explicit reveal command behavior
- external secret manager integration model
- exact binding credential materialization schema

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

## Future Catalog Source and Trust

Question:

How should non-local catalogs work after Phase 1?

Accepted direction:

- Phase 1 supports repo-shipped reference catalog entries
- Phase 1 supports user-configured local filesystem catalog paths
- user-created local catalog entries are allowed
- local catalog files are trusted local-owner input
- App and Service manifests carry minimal catalog metadata in Phase 1
- a separate catalog index is deferred

Deferred:

- Git repositories
- OCI artifacts or registries
- remote indexes
- signed catalogs
- private remote catalogs
- remote catalog trust policy
- package sandboxing guarantees

Need to decide:

- signing/verifying catalog entries
- private catalog credentials
- catalog versioning
- catalog update behavior
- remote catalog source format
- future separate catalog index format, if needed
- compatibility metadata

## Draft Manifest Naming Details

Question:

What naming and cleanup conventions should temporary draft manifests use while Nephos is designing manifest schemas?

Accepted direction:

- temporary draft manifests are allowed during schema design
- temporary draft manifests live under `.agents/drafts/manifests/`
- they must be clearly marked non-canonical
- they must not live under `schemas/`
- they must not live under `examples/`
- they must not be treated as source of truth
- they must be deleted, moved, or converted after shape approval

Need to decide:

- naming convention
- cleanup policy after schema acceptance

## Backend and CLI Packaging

Question:

How should the backend and CLI be packaged and distributed?

Accepted direction:

- backend/control plane lives in `nephos`
- CLI lives in `../nephos-cli`
- backend Phase 1 distribution is local development process plus backend container image
- full installer packaging is deferred
- CLI workflow belongs to the separate CLI repository
- Phase 1 has backend/CLI version awareness without strict compatibility blocking

Need to decide:

- backend package layout
- backend container image strategy
- CLI installation path
- release process across the two repositories
- future strict compatibility matrix

## Local Development Workflow Details

Question:

What are the exact local development commands and conventions for Nephos?

Accepted direction:

- `uv` is the canonical backend Python workflow
- CLI points at local backend/API during development

Need to decide:

- exact `uv` commands
- whether to use Makefile/task runner wrappers
- how SQLite state is initialized/reset
- how migrations are run locally
- how K3s is started/reset for local development
- how `../nephos-cli` points to a local backend

## Testing Details

Question:

What exact test commands, tags, and CI boundaries should Nephos use?

Accepted direction:

- `pytest` for backend tests
- `ruff` for backend linting/formatting checks
- mocks/fakes for unit tests
- real K3s for Kubernetes integration tests
- CLI tests live in the separate CLI repository

Need to decide:

- exact test command names
- pytest marker names
- integration test setup/teardown
- whether CI runs K3s integration tests by default
- fixture strategy for Kubernetes clients
- coverage expectations

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

What exact command spelling, status output, and manifest sketches should define the Paperless + PostgreSQL reference scenario?

Accepted direction:

- Paperless App
- PostgreSQL Service
- local filesystem catalog
- Nephos manifests
- Paperless requires only PostgreSQL in Phase 1 reference scenario
- capability binding
- basic ingress intent
- lifecycle install/start/stop/remove/destroy
- data preserved on stop/remove
- destroy requires destructive confirmation when persistent data exists
- include Service dependency impact
- attempting to stop PostgreSQL while Paperless depends on it is blocked unless forced and shows an impact list
- use illustrative route placeholder such as `paperless.<local-domain>`

Need to decide:

- exact catalog directory layout
- exact manifest filenames
- exact App manifest fields
- exact Service manifest fields
- exact commands
- expected status outputs
- namespace names
- secret names
- exact ingress hostname policy
- data preservation checks
