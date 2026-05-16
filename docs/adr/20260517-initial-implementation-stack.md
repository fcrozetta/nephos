# Initial Implementation Stack

- Status: accepted
- Date: 2026-05-17
- Tags: stack, python, fastapi, cli, sqlite, migrations

## Context and Problem Statement

Nephos needs an initial implementation stack that supports the platform control-plane model without collapsing into raw Kubernetes scripting.

The stack must preserve the boundary:

intent -> desired state -> reconcile into Kubernetes

The repository boundary is also part of the decision: this repository owns the backend/control-plane work, while the CLI is a separate repository.

## Decision

Use Python for the Nephos backend.

Use FastAPI for the Nephos API.

Use SQLite as the Phase 1 canonical desired-state database.

Use simple explicit SQL migrations.

Use the official Python Kubernetes client.

Use an API-owned in-process reconciler for Phase 1.

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

The backend/control-plane implementation belongs in this repository.

CLI implementation belongs in `../nephos-cli`.

The CLI must use the Nephos API/local controller as its product boundary.

The backend must expose stable enough API contracts for the CLI to operate without embedding backend internals.

Packaging/distribution, local development workflow, and final test conventions still need more explicit documentation before implementation begins.
