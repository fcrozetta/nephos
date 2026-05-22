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

`NEPHOS_API_KUBECONFIG` and `NEPHOS_API_KUBE_CONTEXT` are optional overrides for backend runtime and K3s integration tests.

If those variables are unset, the backend and tests use the active standard kubeconfig/context resolution.

Do not add a backend local config file or DB-stored bootstrap config for API 0.0.1.

Local development should run the backend as a local process through `uv run nephos-api serve`.

The CLI should point at the local backend/API during development.

Cluster setup and K3s lifecycle are user-managed or `nephos-cli`-managed for now.

`nephos-api` must not install, start, stop, reset, or destroy K3s.

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

Use real K3s for Kubernetes integration tests.

Unit tests should not require a Kubernetes cluster.

Integration tests that verify reconciliation into Kubernetes should run against K3s.

Use pytest markers:

- `unit`
- `integration`
- `k3s`

Tests marked `k3s` require a real K3s cluster and should also be marked `integration`.

K3s integration tests require a pre-existing reachable K3s cluster.

K3s integration tests must not install, start, stop, reset, or destroy K3s.

K3s integration tests require explicit opt-in:

```bash
NEPHOS_API_RUN_K3S_TESTS=1 uv run pytest -m k3s
```

K3s integration test preflight must verify:

- `NEPHOS_API_RUN_K3S_TESTS=1`
- Kubernetes API reachability

The initial safety guard is explicit opt-in plus API reachability.

Stricter allowed-context/server checks may be added later.

Default backend test command:

```bash
uv run pytest -m "not k3s"
```

Explicit K3s integration test command:

```bash
uv run pytest -m k3s
```

Default CI runs unit and non-K3s tests only.

K3s integration tests are local/manual until a later CI decision defines a K3s job.

K3s integration tests use generated test namespaces.

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

- exact generated K3s test namespace name format
- stricter allowed-context/server safety checks beyond opt-in and API reachability
- future K3s CI job shape, if K3s integration is added to CI
- exact Kubernetes client fixture implementation
- exact `../nephos-cli` local backend configuration convention
- exact `nephos-cli` cluster setup/reset workflow
- backend container image layout
- backend image registry/release process
- cross-repo release process
- CLI repository workflow details
