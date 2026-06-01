# Nephos Development Workflow

## Repository Ownership

This repository is the backend/API repository and should be referred to as `nephos-api` when distinguishing it from the CLI.

`nephos-api` owns backend/control-plane development.

The CLI lives in the separate `nephos-cli` repository:

- GitHub: `https://github.com/fcrozetta/nephos-cli`
- Local path: `../nephos-cli`

CLI implementation, CLI linting, CLI tests, and CLI release workflow belong in the CLI repository.

Do not add CLI implementation code to this repository unless Fer explicitly changes the repository boundary.

When documentation says `nephos <command>`, it refers to the user-facing `nephos-cli` product command.

Backend-local development/ops commands in `nephos-api` must not use the `nephos <command>` spelling.

## Backend Local Development

Use `uv` as the canonical Python workflow for backend development.

Backend package layout:

- `src/nephos_api/`

FastAPI app entrypoint:

- `nephos_api.main:app`

Backend-local console command:

- `nephos-api`

The backend stack remains:

- Python
- FastAPI
- SQLite
- simple explicit SQL migrations
- plain SQL through a small repository/data-access layer
- official Python Kubernetes client

Before the first usable version, local development may destroy and recreate the SQLite database.

Initial schema should live in `migrations/0000_initial.sql`.

Forward-compatible migration discipline starts after the first usable version is established.

Accepted backend-local development commands:

```bash
uv run nephos-api init
uv run nephos-api db migrate
uv run nephos-api db reset --force
uv run nephos-api serve
```

Backend bootstrap configuration for API 0.0.1 uses environment variables only.

Accepted backend bootstrap environment variables:

- `NEPHOS_API_DB_PATH`
- `NEPHOS_API_CATALOG_ROOTS`
- `NEPHOS_API_KUBECONFIG`
- `NEPHOS_API_KUBE_CONTEXT`

If `NEPHOS_API_DB_PATH` is unset, the SQLite database path defaults to `.nephos/state/nephos.db` relative to the backend process working directory.

If `NEPHOS_API_CATALOG_ROOTS` is set, it is parsed as a platform path-list of additional local catalog roots.

Kubernetes target selection uses normal Kubernetes client configuration resolution by default.

`NEPHOS_API_KUBECONFIG` and `NEPHOS_API_KUBE_CONTEXT` are optional overrides for backend runtime and Kubernetes integration tests.

`NEPHOS_API_INGRESS_CLASS` optionally overrides generated Kubernetes
`ingressClassName`; otherwise Nephos auto-detects a single/default cluster
`IngressClass`.

If those variables are unset, the backend and tests use the active standard kubeconfig/context resolution.

Do not add a backend local config file or DB-stored bootstrap config for API 0.0.1.

Local development should initialize backend state through `uv run nephos-api init`
and run the backend as a local process through `uv run nephos-api serve`.

`uv run nephos-api init` ensures one default internal platform domain. The
default internal domain is `NEPHOS_API_INTERNAL_DOMAIN` or `nephos.local`; use
`--internal-domain` to override it.

For local browser testing without `/etc/hosts`, use a resolvable suffix such as
`nephos.localhost`.

The CLI should point at the local backend/API during development.

Cluster setup and lifecycle are user-managed or `nephos-cli`-managed for now.

`nephos-api` must not install, start, stop, reset, or destroy the selected Kubernetes cluster.

Migration and reset commands are backend-local `nephos-api` development/ops commands.

They are not product CLI commands and must not use the `nephos <command>` spelling.

API 0.0.1 implementation order:

1. migration and database layer
2. API skeleton
3. catalog loader
4. reconciler

## Testing Baseline

Use `pytest` for backend tests.

Use `ruff` for backend linting/formatting checks.

Use mocks or fakes for backend unit tests.

Use a real selected Kubernetes cluster for Kubernetes integration tests.

Unit tests should not require a Kubernetes cluster.

Integration tests that verify reconciliation into Kubernetes should run against the selected Kubernetes context.

Use pytest markers:

- `unit`
- `integration`
- `kubernetes`

Tests marked `kubernetes` require a real selected Kubernetes cluster and should also be marked `integration`.

Kubernetes integration tests require a pre-existing reachable selected Kubernetes cluster.

Kubernetes integration tests must not install, start, stop, reset, or destroy the selected cluster.

Kubernetes integration tests require explicit opt-in:

```bash
NEPHOS_API_RUN_KUBERNETES_TESTS=1 uv run pytest -m kubernetes
```

Kubernetes integration test preflight must verify:

- `NEPHOS_API_RUN_KUBERNETES_TESTS=1`
- Kubernetes API reachability

The initial safety guard is explicit opt-in plus API reachability.

Stricter allowed-context/server checks may be added later.

Default backend test command:

```bash
uv run pytest -m "not kubernetes"
```

Explicit Kubernetes integration test command:

```bash
uv run pytest -m kubernetes
```

Default CI runs unit and non-Kubernetes-runtime tests only.

Kubernetes integration tests are local/manual until a later CI decision defines a runtime job.

Kubernetes integration tests use generated test namespaces.

Generated test namespaces and test-owned resources must use:

```text
app.kubernetes.io/managed-by: nephos
```

Test cleanup may delete only generated test namespaces/resources that it created and labeled.

Makefile and task-runner wrappers are deferred.

Raw `uv run nephos-api ...`, `uv run pytest ...`, and `uv run ruff ...` commands are the accepted local command surface until implementation proves wrappers are useful.

## Packaging And Distribution

Phase 1 backend distribution is:

- local development process for developers
- backend container image for runtime packaging

Full installer packaging is deferred.

Backend and CLI packaging are related but owned separately.

The CLI repository should document its own install, test, lint, and release workflow.

## Version Awareness

Phase 1 should have backend/CLI version awareness but no strict compatibility blocking.

The backend should expose a version endpoint.

The CLI should report:

- CLI version
- backend version

The CLI may warn when backend version is unknown, older, or newer than expected.

The CLI should not block state-mutating commands solely because of version mismatch in Phase 1.

Strict compatibility blocking is deferred until the backend API, manifest schema, and release matrix are more stable.

Future strict compatibility behavior requires an explicit decision.

## Still Open

- exact generated Kubernetes test namespace name format
- stricter allowed-context/server safety checks beyond opt-in and API reachability
- future Kubernetes runtime CI job shape, if Kubernetes integration is added to CI
- exact Kubernetes client fixture implementation
- exact `../nephos-cli` local backend configuration convention
- exact `nephos-cli` cluster setup/reset workflow
- backend container image layout
- backend image registry/release process
- cross-repo release process
- CLI repository workflow details
