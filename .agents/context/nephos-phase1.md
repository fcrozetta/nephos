# Nephos Phase 1

## Accepted Scope So Far

Phase 1 is local-first and single-owner.

Phase 1 targets a selected single-node Kubernetes cluster.

Backend/control plane:

- `nephos` repository
- Python
- FastAPI
- `uv` backend workflow
- SQLite canonical desired-state database
- simple explicit SQL migrations
- plain SQL through a small repository/data-access layer
- initial schema file `migrations/0000_initial.sql`
- destructive local SQLite reset allowed before the first usable version
- official Python Kubernetes client
- normal Kubernetes client config resolution by default
- optional `NEPHOS_API_KUBECONFIG` and `NEPHOS_API_KUBE_CONTEXT`
- API-owned in-process reconciler
- persisted SQLite reconciliation requests
- one serialized background reconciler worker initially
- reconciliation request states `pending`, `running`, `succeeded`, `failed`, and `blocked`
- `pytest` backend tests
- `ruff` backend linting/formatting checks
- mocks/fakes for unit tests
- real selected Kubernetes cluster for Kubernetes integration tests
- Kubernetes integration tests require `NEPHOS_API_RUN_KUBERNETES_TESTS=1`
- default tests and default CI exclude Kubernetes runtime integration

CLI:

- separate `nephos-cli` repository
- Python
- Typer
- trusted local client
- talks to Nephos API/local controller
- owns its own test/lint/release workflow
- version-aware with backend but no strict compatibility blocking

Runtime:

- selected Kubernetes context as the real backend
- single-node Kubernetes target
- Kubernetes runtime substrate
- minimal cluster lifecycle support
- cluster setup and lifecycle are user-managed or `nephos-cli`-managed for now
- `nephos-api` reconciles into Kubernetes but must not install, start, stop, reset, or destroy the selected cluster
- no CRD-first model
- no GitOps source-of-truth model
- one namespace per App instance
- one namespace per Service instance
- `nephos-system` namespace for Nephos control-plane/runtime support components
- no default-deny NetworkPolicy

State:

- Nephos API/database is canonical desired state
- YAML is import/export only

Catalog and packaging:

- separate App and Service Nephos manifests
- YAML Nephos manifests
- Kubernetes-like `apiVersion`/`kind`/`metadata`/`spec` envelope with Nephos semantics
- `apiVersion: nephos.pro/v1alpha1`
- accepted manifest kinds `App` and `Service`
- strict DNS-label style machine identifiers for manifest `metadata.name`, binding aliases, route names, instance slugs, and catalog entry slugs
- default installed instance names equal catalog manifest `metadata.name`
- explicit user-provided instance names are allowed at install time
- name collisions fail and require explicit input
- generated Kubernetes names must fit resource limits after prefixes are added
- directory-per-entry local catalog layout with `app.yaml` and `service.yaml`
- Helm chart runtime packaging underneath manifests
- internal Python Pulumi providers as the forward execution boundary
- direct Helm is secondary for Services
- raw Kubernetes manifest fallback
- raw Kubernetes manifest fallback shape deferred until first needed
- local filesystem catalog from day one
- repo-shipped reference catalog entries
- user-configured local filesystem catalog paths
- user-created local catalog entries allowed
- local catalog files trusted as local-owner input
- minimal catalog metadata carried in App/Service manifests
- no separate catalog index
- tiny repo-shipped reference catalog
- Phase 1 App config option types are `string`, `integer`, `boolean`, and `enum`
- config options use required `name` and `type`, plus optional `label`, `description`, `default`, and `required`
- config option `required` defaults to `false`
- enum config options use object values with `value` and `label`
- `secret` App config option type deferred
- config validation bounds such as min/max/regex/length deferred
- config runtime mapping happens through `spec.runtime.values.mappings[]`
- Phase 1 runtime mapping source kinds are `config` and `binding`
- runtime mapping target is `to.helmValue` as a dot path
- missing mapping sources block reconciliation with a reason
- unknown manifest fields rejected once canonical schemas exist
- no schema files until Fer approves concrete validation schema
- alpha backbone Service scope is PostgreSQL, Zitadel, SeaweedFS, ArcadeDB, then the first dogfood App
- Pulumi is the alpha runtime path
- Aspire is out of scope
- Helm may be used underneath Pulumi-backed Service providers when it is the easiest install path
- Helm charts do not define Nephos Service behavior
- App requirements and Service provisions match by `capability + protocol`
- PostgreSQL provides `sql/postgres`
- ArcadeDB provides `sql/arcadedb`, `opencypher/bolt`, `opencypher/n4j`, optional `gremlin/gremlin`, and optional `mongo/mongo` when enabled
- SeaweedFS provides `object-storage/s3`
- Zitadel provides `oidc/oidc` and `service-account/jwt`

Services:

- shared/global Service instances first
- dedicated Service instances reserved as concept
- Service operations reserved but bounded
- internal typed Service handlers may support minimal accepted provisioning work
- no general user-facing Service operation API or CLI UX
- Service surfaces are allowed for the narrow Zitadel alpha use case
- Zitadel login/admin UI are Service surfaces/routes, not a separate App

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
- install through `POST /apps` and `POST /services`
- public paths use installed instance slugs such as `/apps/paperless` and `/services/postgres`
- lifecycle actions through `POST /apps/{appInstance}/actions/{action}` and `POST /services/{serviceInstance}/actions/{action}`
- destroy through `POST .../actions/destroy` with explicit confirmation, not plain `DELETE`
- dependency-blocked Service lifecycle actions return `409 Conflict` with impact lists unless forced
- mutating responses prefer `202 Accepted` with `{ resource, reconciliation, status? }`

Ingress and secrets:

- Traefik may be the default ingress controller
- Traefik does not provide local DNS resolution
- local visibility mode
- Nephos-owned route intent
- Kubernetes-owned Ingress resources
- generated Ingress resources set `ingressClassName` from env override or single/default cluster `IngressClass`
- multiple configured ingress root domains
- one default/canonical ingress root domain
- at least one root domain for generated route hosts
- ingress root domains stored as platform desired state in the Nephos API/database
- ingress root domains managed through Nephos API/CLI platform configuration operations
- root domain config uses `name`, `domain`, and `default`
- root domain API path is `/platform/config/domains`
- host rules generated for each configured root domain
- default route host pattern `<app-instance>.<root-domain>`
- non-default route host pattern `<route>.<app-instance>.<root-domain>`
- App status shows canonical URL plus aliases
- setup creates initial platform configuration before Apps are installed
- backend-local `uv run nephos-api init` creates the initial internal root domain
- default internal root domain fallback is `nephos.local`
- `NEPHOS_API_INTERNAL_DOMAIN` can provide a no-hosts local suffix such as `nephos.localhost`
- later user-facing setup UX is deferred to `nephos-cli`
- path-based App routing out of scope
- HTTP-only Nephos-managed ingress
- no generic Service admin routes through Nephos ingress
- Zitadel login/admin UI are the accepted narrow Service-surface exception
- stopped Apps keep route intent and may keep runtime ingress
- remove/destroy remove runtime ingress
- Kubernetes Secrets for Phase 1
- App binding credentials materialized into App namespaces
- App binding aliases default to `capability` when `as` is omitted
- binding aliases are unique per App manifest and installed App instance
- binding Secret names use `nephos-bind-<alias>` in the consuming App namespace
- rebinding updates the same binding Secret name after explicit reconciliation or confirmation
- binding Secrets include `app.kubernetes.io/managed-by: nephos`, `nephos.pro/app-instance`, `nephos.pro/service-instance`, `nephos.pro/capability`, and `nephos.pro/binding-alias`
- PostgreSQL `app-secret` outputs use exact lowercase keys `host`, `port`, `database`, `username`, `password`, and `uri`
- Service-internal/admin secrets in Service namespaces
- stop/remove preserve Secrets
- destroy deletes Secrets for the destroyed entity
- secret values redacted by default

Packaging/distribution:

- backend local development process
- backend container image for runtime packaging
- full installer packaging deferred

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
- alpha reference/dogfood catalog should exercise local filesystem catalog/manifest flow
- Paperless requires only PostgreSQL in the Phase 1 reference scenario
- bind Paperless to the `sql/postgres` capability/protocol exposed by PostgreSQL
- PostgreSQL provisions an app-scoped database/user for Paperless
- Nephos materializes PostgreSQL binding outputs into the Paperless App namespace
- PostgreSQL binding fields are `host`, `port`, `database`, `username`, `password`, and `uri`
- expose Paperless through local route intent using examples such as `paperless.nephos.local` and `paperless.nephos.fcrozetta.app`
- stop/start preserves data
- remove preserves persistent data and metadata
- remove preserves app-scoped PostgreSQL resources and binding metadata
- destroy deletes persistent data associated with the App lifecycle after destructive confirmation
- destroy deletes app-scoped PostgreSQL resources created for Paperless after destructive confirmation
- attempting to stop PostgreSQL while Paperless depends on it is blocked unless forced and shows an impact list

## Still To Define

- exact CLI command spelling for root domain operations
- whether setup is interactive, flag-driven, or both
- exact setup command spelling in `nephos-cli`
- setup idempotency behavior
- App install behavior when setup is missing
- binding Secret rotation behavior
- backup guarantees
- exact generated Kubernetes test namespace name format
- stricter Kubernetes test allowed-context/server safety checks
- future Kubernetes runtime CI job shape, if Kubernetes integration is added to CI
- exact `nephos-cli` cluster setup/reset workflow
- local CLI backend configuration workflow
- packaging/distribution
- future remote catalog trust/signing/update behavior
- backend image layout and registry
- cross-repo release process
- exact reference scenario command spelling and status output
