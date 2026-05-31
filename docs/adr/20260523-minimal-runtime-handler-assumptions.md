# Minimal Runtime Handler Assumptions

- Status: draft
- Date: 2026-05-23
- Tags: runtime, helm, kubernetes, provisioning, postgres, draft

## Context and Problem Statement

API 0.0.1 has desired-state persistence, catalog loading, installed App and Service records, bindings, lifecycle mutations, manual reconciliation requests, and a persisted reconciliation worker shell.

The next implementation step needs a real runtime path for the Paperless plus PostgreSQL reference flow, but two details are not yet accepted as durable architecture:

- Helm execution mechanics.
- PostgreSQL app-scoped provisioning handler boundaries.

Fer selected a minimal implementation path that proceeds with explicit draft assumptions instead of waiting for a full accepted runtime ADR.

This ADR is intentionally draft. It records implementation assumptions for the first runtime spike and must not be treated as an accepted durable contract until Fer confirms or replaces it.

## Draft Assumptions

### Helm execution

The API-owned reconciler may invoke the local `helm` CLI as a subprocess for the first runtime spike.

Initial command shape:

```text
helm upgrade --install <release> <chart-name> \
  --repo <chart-repository> \
  --version <chart-version> \
  --namespace <namespace> \
  --create-namespace \
  --wait \
  --timeout <timeout> \
  -f <generated-values-file>
```

Initial release and namespace names are derived from installed instance slugs:

- App namespace and release: `app-<app-slug>`
- Service namespace and release: `svc-<service-slug>`

Helm remains below the Nephos product model. Users do not provide arbitrary Helm commands through Nephos API 0.0.1.

Generated Helm values come only from accepted Nephos semantic inputs:

- App config values.
- Binding output fields.
- Future route/storage values only after explicit decisions.

Missing mapping sources block reconciliation with status evidence.

### Kubernetes API use

The runtime handler may use the official Python Kubernetes client for namespace and Secret materialization.

Kubernetes configuration follows existing backend settings:

- normal kubeconfig resolution by default
- optional `NEPHOS_API_KUBECONFIG`
- optional `NEPHOS_API_KUBE_CONTEXT`

The API must not install, start, stop, reset, or destroy K3s.

### PostgreSQL app-scoped provisioning

The first typed PostgreSQL provisioning handler is internal backend logic, not a user-facing Service operation API.

For a `postgres` binding with `app-secret` output, the runtime handler may materialize these logical fields into the consuming App namespace Secret:

- `host`
- `port`
- `database`
- `username`
- `password`
- `uri`

Initial generated Secret name remains:

```text
nephos-bind-<binding-alias>
```

Initial Postgres endpoint assumption:

```text
svc-<service-slug>-postgresql.svc-<service-slug>.svc.cluster.local:5432
```

Initial database and username derivation replaces hyphens with underscores in the App slug.

The handler should reuse an existing binding Secret if present so credentials remain stable across retries.

Actual SQL-level database/user creation remains draft-bound in this spike. If the handler cannot safely perform SQL provisioning from known chart/admin credentials, it must report that clearly in status evidence rather than pretending the database was created.

### Lifecycle coverage in the first runtime spike

The first runtime implementation may support runtime apply for these actions:

- `service.install`
- `service.reconcile`
- `service.start`
- `app.install`
- `app.reconcile`
- `app.start`
- `binding.reconcile`

The first runtime implementation may still block these actions until teardown/scale semantics are accepted and implemented:

- stop
- remove
- destroy

Destroy must not delete Nephos desired-state rows until runtime teardown has succeeded.

## Consequences

This gives API 0.0.1 a concrete runtime path without making Helm or provisioning details canonical.

The implementation must keep status evidence honest when an operation is only partially implemented or rests on a draft assumption.

A later accepted ADR should replace or amend this draft before these mechanics are considered stable public behavior.

## Open Questions

- Whether Helm remains a subprocess or moves behind a library/SDK wrapper.
- Exact Helm timeout and failure classification.
- Exact release naming if generated names approach Kubernetes/Helm limits.
- Exact PostgreSQL chart contract and admin credential discovery.
- Exact SQL provisioning mechanism for app-scoped PostgreSQL database/user creation.
- Whether provisioning outputs should be backed by runtime Secret state only or additional Nephos-managed state.
- Stop/remove/destroy runtime teardown details for Helm releases, PVCs, Secrets, and app-scoped PostgreSQL resources.
