# Nephos Phase 1

## Accepted Scope So Far

Phase 1 is local-first and single-owner.

Phase 1 targets single-node K3s.

Backend/control plane:

- `nephos` repository
- Python
- FastAPI
- `uv` backend workflow
- SQLite canonical desired-state database
- simple explicit SQL migrations
- official Python Kubernetes client
- API-owned in-process reconciler
- `pytest` backend tests
- `ruff` backend linting/formatting checks
- mocks/fakes for unit tests
- real K3s for Kubernetes integration tests

CLI:

- separate `nephos-cli` repository
- Python
- Typer
- trusted local client
- talks to Nephos API/local controller
- owns its own test/lint/release workflow
- version-aware with backend but no strict compatibility blocking

Runtime:

- K3s default real backend
- single-node K3s target
- Kubernetes runtime substrate
- minimal cluster lifecycle support
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
- directory-per-entry local catalog layout with `app.yaml` and `service.yaml`
- Helm-primary runtime deployment underneath manifests
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
- unknown manifest fields rejected once canonical schemas exist
- no schema files until Fer approves concrete validation schema

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

Ingress and secrets:

- Traefik default ingress controller
- local visibility mode
- Nephos-owned route intent
- Kubernetes-owned Ingress resources
- stopped Apps keep route intent and may keep runtime ingress
- remove/destroy remove runtime ingress
- Kubernetes Secrets for Phase 1
- App binding credentials materialized into App namespaces
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
- reference catalog should exercise local filesystem catalog/manifest flow
- Paperless requires only PostgreSQL in the Phase 1 reference scenario
- bind Paperless to the `postgres` capability exposed by PostgreSQL
- PostgreSQL provisions an app-scoped database/user for Paperless
- Nephos materializes PostgreSQL binding outputs into the Paperless App namespace
- PostgreSQL binding fields are `host`, `port`, `database`, `username`, `password`, and `uri`
- expose Paperless through local route intent using a placeholder like `paperless.<local-domain>`
- stop/start preserves data
- remove preserves persistent data and metadata
- remove preserves app-scoped PostgreSQL resources and binding metadata
- destroy deletes persistent data associated with the App lifecycle after destructive confirmation
- destroy deletes app-scoped PostgreSQL resources created for Paperless after destructive confirmation
- attempting to stop PostgreSQL while Paperless depends on it is blocked unless forced and shows an impact list

## Still To Define

- exact namespace slug normalization and labels
- ingress/TLS/local DNS hostname behavior
- binding Secret naming and rotation behavior
- backup guarantees
- local development workflow
- packaging/distribution
- future remote catalog trust/signing/update behavior
- exact developer commands
- backend image layout and registry
- cross-repo release process
- exact reference scenario command spelling and status output
