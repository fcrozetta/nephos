# Local Development, Testing, and Distribution

- Status: accepted
- Date: 2026-05-17
- Tags: development, testing, packaging, cli, phase-1

## Context and Problem Statement

Nephos needs a practical development and testing baseline before implementation starts.

The backend/control-plane repository and CLI repository are separate, so local workflow, test ownership, packaging, and version compatibility need explicit boundaries.

## Decision

Use `uv` as the canonical backend Python workflow in this repository.

Backend-local command spelling is refined by [Backend Package and Dev Command Shape](20260522-backend-package-and-dev-command-shape.md).

Accepted backend-local commands:

```bash
uv run nephos-api db migrate
uv run nephos-api db reset --force
uv run nephos-api serve
```

Use `pytest` and `ruff` as the required backend test/lint baseline.

Use mocks/fakes for backend unit tests.

Use real K3s for Kubernetes integration tests.

Use pytest markers:

- `unit`
- `integration`
- `k3s`

Tests marked `k3s` require real K3s and should also be marked `integration`.

Default backend test command:

```bash
uv run pytest -m "not k3s"
```

Explicit K3s integration test command:

```bash
uv run pytest -m k3s
```

Makefile and task-runner wrappers are deferred for API 0.0.1.

Phase 1 backend distribution is:

- local development process for developers
- backend container image for runtime packaging

Full installer packaging is deferred.

The CLI has its own test, lint, and release workflow in the separate `nephos-cli` repository.

This repository must not become the owner of CLI implementation workflow.

## CLI And Backend Version Awareness

Phase 1 should have version awareness without strict compatibility blocking.

The backend should expose a version endpoint.

The CLI should be able to report:

- CLI version
- backend version

The CLI may warn when the backend version is unknown, older, or newer than expected.

The CLI should not block state-mutating commands solely because of version mismatch in Phase 1.

Strict compatibility blocking is deferred until Nephos has a more stable backend API, manifest schema, and release matrix.

Future strict compatibility rules require an explicit decision.

## Decision Drivers

- Keep Phase 1 shippable.
- Preserve the backend/CLI repository boundary.
- Avoid pretending the API is stable before the model settles.
- Test Kubernetes reconciliation against real K3s where runtime behavior matters.
- Keep unit tests fast and isolated.

## Consequences

Backend implementation can start with a clear Python toolchain.

Unit tests can run without a Kubernetes cluster.

Integration tests require K3s and should be separated from fast unit tests.

K3s-dependent tests do not run in the default backend test command.

The backend can be packaged for runtime without solving the full installer story.

Cross-repo release discipline is still needed later.

The CLI/backend mismatch behavior is intentionally permissive in Phase 1, so API changes must still be handled carefully during development.

## Notes

Do not add CLI implementation code to this repository.

Do not add strict CLI/backend compatibility gates without a new decision.

API bootstrap environment, migration runner, catalog root, SQLite timeout, and wrapper details are refined by [API Bootstrap Mechanics](20260522-api-bootstrap-mechanics.md).
