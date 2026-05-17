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
- Service manifests declare logical binding outputs, not final consuming Secret names
- Nephos chooses deterministic Secret names from binding identity
- stop/remove preserve Secrets
- destroy deletes Secrets for the destroyed entity
- secret values are redacted by default

Need to decide:

- exact binding Secret naming algorithm
- exact labels/annotations
- rotation behavior
- whether/how secrets are included in Nephos state backup
- future explicit reveal command behavior
- external secret manager integration model
- non-PostgreSQL Secret key serialization
- binding credential materialization schemas beyond accepted PostgreSQL logical fields

## Manifest Schema Details

Question:

What are the concrete App and Service manifest schemas?

Accepted direction:

- YAML manifests
- `apiVersion: nephos.pro/v1alpha1`
- Kubernetes-like envelope with Nephos semantics:
  - `apiVersion`
  - `kind`
  - `metadata`
  - `spec`
- accepted manifest kinds are `App` and `Service`
- directory-per-entry catalog layout:
  - `catalog/apps/<app-slug>/app.yaml`
  - `catalog/services/<service-slug>/service.yaml`
- separate App and Service Nephos manifest formats
- Helm-primary runtime deployment references
- raw Kubernetes manifest fallback
- App manifests use `metadata.name`, optional `metadata.displayName`, optional `metadata.description`, optional `metadata.version`, `spec.requires[]`, `spec.routes[]`, `spec.config.options[]`, and `spec.runtime`
- `spec.requires[]` supports `capability`, optional `as`, and optional `provider`
- Service manifests use `metadata.name`, optional `metadata.displayName`, optional `metadata.description`, optional `metadata.version`, `spec.provides[]`, `spec.bindings.outputs[]`, `spec.provisioning.mode`, `spec.runtime`, and `spec.operations[]`
- `spec.provides[]` supports `capability`, optional `as`, and optional `version`
- `spec.bindings.outputs[]` starts with `target: app-secret`
- Phase 1 supports only `app-secret` as the binding output target
- PostgreSQL binding outputs use logical fields `host`, `port`, `database`, `username`, `password`, and `uri`
- Service manifests declare logical binding outputs, not final consuming Secret names
- Nephos chooses deterministic Secret names from binding identity
- Apps consume bindings through symbolic aliases such as `as: database`
- Nephos maps binding outputs into runtime values through the reserved `spec.runtime.values.mappings[]` lane
- PostgreSQL binding output fields are capability-defined and do not use a manifest `fields:` syntax in Phase 1
- PostgreSQL `app-secret` outputs use exact lowercase Secret keys `host`, `port`, `database`, `username`, `password`, and `uri`
- Phase 1 config option types are `string`, `integer`, `boolean`, and `enum`
- `secret` App config option type is deferred
- App config must not become a second credential path beside bindings and generated Service credentials
- arbitrary object and array config option values are not supported in Phase 1
- Phase 1 provisioning modes are `app-scoped-resource` and `none`
- `app-scoped-resource` means the Service creates a resource for the consuming App inside the Service instance
- `none` means no Service-side resource is created for the binding
- provisioning is a typed backend/API-owned contract, not arbitrary user-facing shell
- remove preserves provisioned Service-side resources created for an App
- destroy deletes provisioned Service-side resources created for an App after destructive confirmation
- `spec.operations[]` is reserved
- App says it needs a capability, Service says it provides a capability, Nephos resolves and creates bindings outside the manifest
- routes declare identity/visibility/target, not full hostnames
- Nephos derives hostnames from App instance name, route name, visibility, and configured domain policy
- Phase 1 installable catalog entries require `apiVersion`, `kind`, `metadata.name`, and `spec.runtime`
- App `spec.requires[]`, `spec.routes[]`, and `spec.config.options[]` default to empty lists
- Service `spec.provides[]` is required and must be non-empty
- Service `spec.provisioning.mode` is required and must be either `none` or `app-scoped-resource`
- `spec.operations[]` defaults to an empty list
- PostgreSQL Service `spec.bindings.outputs[]` must include an `app-secret` output
- unknown manifest fields are rejected once canonical schemas exist
- raw Kubernetes manifest fallback shape is deferred until first needed
- canonical examples remain blocked until manifest validation plus command/status shape are stable enough
- no schema file until Fer approves the concrete validation schema

Need to decide:

- config option object shape
- binding output targets beyond `app-secret`
- non-PostgreSQL binding output payload schemas
- future optional binding output payload declaration syntax, if needed
- non-PostgreSQL Secret key serialization
- exact deterministic Secret naming algorithm
- required/default behavior for Services that expose capabilities without binding outputs
- raw manifest runtime reference shape when first needed
- validation rules beyond unknown-field rejection
- command/status shape needed before promoting draft sketches into canonical examples

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
- PostgreSQL provisions an app-scoped database/user for Paperless
- Nephos materializes PostgreSQL binding outputs into Paperless App namespace
- PostgreSQL binding fields are `host`, `port`, `database`, `username`, `password`, and `uri`
- basic ingress intent
- lifecycle install/start/stop/remove/destroy
- data preserved on stop/remove
- remove preserves app-scoped PostgreSQL resources and binding metadata
- destroy deletes app-scoped PostgreSQL resources created for Paperless after destructive confirmation
- destroy requires destructive confirmation when persistent data exists
- include Service dependency impact
- attempting to stop PostgreSQL while Paperless depends on it is blocked unless forced and shows an impact list
- use illustrative route placeholder such as `paperless.<local-domain>`

Need to decide:

- exact App manifest examples
- exact Service manifest examples
- exact commands
- expected status outputs
- namespace names
- binding Secret naming algorithm
- exact ingress hostname policy
- data preservation checks
