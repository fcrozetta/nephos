# Initial Implementation Stack

- Status: accepted
- Date: 2026-05-17
- Tags: stack, python, fastapi, cli, sqlite, migrations

## Context and Problem Statement

Nephos needs an initial implementation stack that supports the platform control-plane model without collapsing into raw Kubernetes scripting.

The stack must preserve the boundary:

intent -> desired state -> reconcile into Kubernetes

The repository boundary is also part of the decision: this backend/API repository owns the backend/control-plane work, while the CLI is a separate repository.

When distinguishing repositories, refer to this repository as `nephos-api` and the CLI repository as `nephos-cli`.

## Decision

Use Python for the Nephos backend.

Use `src/nephos_api/` as the backend Python package layout.

Use FastAPI for the Nephos API.

Use `nephos_api.main:app` as the FastAPI app entrypoint.

Use SQLite as the Phase 1 canonical desired-state database.

Use simple explicit SQL migrations.

Use plain SQL through a small repository/data-access layer.

Do not introduce a full ORM for API 0.0.1.

Before the first usable version, local development may destroy and recreate the SQLite database.

Initial schema should live in `migrations/0000_initial.sql`.

Use the official Python Kubernetes client.

Use `uv` as the canonical backend Python workflow.

Expose backend-local development/ops commands through `nephos-api`.

Accepted backend-local command shapes:

```bash
uv run nephos-api db migrate
uv run nephos-api db reset --force
uv run nephos-api serve
```

Use `pytest` and `ruff` as the backend test/lint baseline.

Use an API-owned in-process reconciler for Phase 1.

API 0.0.1 reconciliation runs through a background worker over persisted SQLite reconciliation requests.

Mutating API calls return after the desired-state transaction and reconciliation request commit.

The API should not wait for Kubernetes convergence before returning.

Defer the Web UI and frontend framework decision.

Use Python and Typer for the CLI, but implement the CLI in the separate `nephos-cli` repository:

- GitHub: `https://github.com/fcrozetta/nephos-cli`
- Local path: `../nephos-cli`

Do not implement CLI code in this repository unless the repository boundary changes by explicit decision.

## Decision Drivers

- Python-first project defaults.
- FastAPI as the preferred API baseline.
- Local-first desired-state persistence.
- Low operational burden in Phase 1.
- Clear separation between CLI UX and backend/control-plane ownership.
- Avoiding direct unstructured CLI-to-Kubernetes mutation logic.

## Considered Options

### Python/FastAPI backend with separate Python/Typer CLI

Pros:

- Fits the project defaults.
- Keeps the backend and CLI independently configurable.
- Supports local-first API/database ownership.
- Preserves a future path to Web UI and daemon/controller extraction.

Cons:

- Requires two repositories to stay aligned.
- Requires an explicit API contract between backend and CLI.

### Single repository backend and CLI

Pros:

- Simpler early code sharing.
- Less initial repository setup.

Cons:

- Conflicts with the accepted repository split.
- Can blur product API boundaries.

### CLI-first Kubernetes mutation layer

Pros:

- Fastest path to visible Kubernetes changes.

Cons:

- Collapses Nephos into a thin Kubernetes wrapper.
- Undermines desired-state persistence.
- Makes future API/UI/controller integration worse.

## Decision Outcome

Chosen option: "Python/FastAPI backend with separate Python/Typer CLI", because it matches the project defaults while preserving the Nephos platform-control-plane boundary.

## Consequences

The backend/control-plane implementation belongs in this repository, `nephos-api`.

CLI implementation belongs in `../nephos-cli`.

When documentation says `nephos <command>`, it refers to the user-facing command implemented by `nephos-cli`.

Backend-local development/ops commands in `nephos-api` must not use the `nephos <command>` spelling.

The accepted backend package and command details are refined in [Backend Package and Dev Command Shape](./20260522-backend-package-and-dev-command-shape.md).

API bootstrap environment, migration runner, catalog root, SQLite timeout, and test marker details are refined by [API Bootstrap Mechanics](./20260522-api-bootstrap-mechanics.md).

The CLI must use the Nephos API/local controller as its product boundary.

The backend must expose stable enough API contracts for the CLI to operate without embedding backend internals.

Backend unit tests use mocks/fakes.

Kubernetes integration tests use real K3s.

Phase 1 backend distribution is a local development process plus backend container image.

The CLI has its own test, lint, packaging, and release workflow in the separate `nephos-cli` repository.

Phase 1 has backend/CLI version awareness but no strict compatibility blocking.
