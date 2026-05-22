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

Local development should run the backend as a local process.

The CLI should point at the local backend/API during development.

The exact developer commands are not finalized yet.

Migration and reset commands are backend-local `nephos-api` development/ops commands.

Exact backend-local command spelling remains open until package/module naming is implemented.

## Testing Baseline

Use `pytest` for backend tests.

Use `ruff` for backend linting/formatting checks.

Use mocks or fakes for backend unit tests.

Use real K3s for Kubernetes integration tests.

Unit tests should not require a Kubernetes cluster.

Integration tests that verify reconciliation into Kubernetes should run against K3s.

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

- exact `uv` commands
- exact Makefile/task runner conventions
- exact local SQLite initialization/reset commands
- exact migration command
- exact K3s startup/reset workflow
- exact integration test tags/markers
- backend container image layout
- backend image registry/release process
- cross-repo release process
- CLI repository workflow details
