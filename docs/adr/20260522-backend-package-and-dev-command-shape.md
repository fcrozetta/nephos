# Backend Package and Dev Command Shape

- Status: accepted
- Date: 2026-05-22
- Tags: backend, package, dev-workflow, cli-boundary, phase-1

## Context and Problem Statement

The initial stack and command-boundary decisions split Nephos across two repositories:

- `nephos-api`: this backend/API repository
- `nephos-cli`: the separate user-facing CLI repository

The remaining implementation blocker is the backend package layout and backend-local command spelling.

The command shape must preserve the repository boundary:

- `nephos <command>` belongs to the user-facing CLI implemented by `nephos-cli`.
- backend-local development and operations commands belong to `nephos-api`.

## Decision

Use `src/nephos_api/` as the Python package layout for this backend/API repository.

Expose a backend-local console command named `nephos-api`.

Use this FastAPI app entrypoint:

```text
nephos_api.main:app
```

Use these accepted backend-local development commands:

```bash
uv run nephos-api init
uv run nephos-api db migrate
uv run nephos-api db reset --force
uv run nephos-api serve
```

These are `nephos-api` development/operations commands, not `nephos-cli` product commands.

Do not document or implement backend-local commands as `uv run nephos ...`.

Start API 0.0.1 implementation in this order:

1. migration and database layer
2. API skeleton
3. catalog loader
4. reconciler

## Considered Options

### `src/nephos_api/`

Pros:

- Matches the repository name.
- Avoids ambiguity with the `nephos` product CLI command.
- Keeps imports clear when both repositories are checked out side by side.

Cons:

- Slightly less elegant than a shorter `nephos` package name.

### `src/nephos/`

Pros:

- Cleaner import namespace.
- Matches the product name.

Cons:

- Blurs the accepted backend/CLI repository boundary.
- Makes local development more ambiguous when `nephos-cli` also exposes the `nephos` command.

### Backend-local `nephos-api` command

Pros:

- Clear that the command belongs to the backend/API repository.
- Avoids collision with the user-facing `nephos` command.
- Gives init, migration, reset, and serve flows one stable local command surface.

Cons:

- Adds a backend-only command that users should not confuse with product CLI UX.

### Only `python -m nephos_api`

Pros:

- Avoids another console script.
- Keeps everything visibly Python/module scoped.

Cons:

- Noisier for common local development operations.
- Easier for docs to drift into inconsistent command spelling.

### Backend-local `nephos` command

Pros:

- Short.

Cons:

- Conflicts with the accepted `nephos-cli` product command boundary.
- Risks turning backend-local operations into product UX by accident.

## Consequences

Implementation scaffolding in this repository should create `src/nephos_api/`.

Backend packaging should expose the `nephos-api` console command.

The FastAPI app should be importable as `nephos_api.main:app`.

Local backend bootstrap should be implemented behind `uv run nephos-api init`.

`init` should apply pending migrations and create the local desired-state
database, then ensure one default internal root domain. If no domain is passed,
the default is `nephos.local`.

```bash
uv run nephos-api init --internal-domain <dns-suffix>
```

It should not install Apps, install Services, mutate Kubernetes, or create
runtime reconciliation requests.

Local migration and reset behavior should be implemented behind `uv run nephos-api db migrate` and `uv run nephos-api db reset --force`.

Local backend startup should be implemented behind `uv run nephos-api serve`.

Architecture docs must keep `nephos-api` backend-local commands separate from `nephos-cli` product commands.

API 0.0.1 implementation should begin with the migration/database layer before API endpoints, catalog loading, or reconciliation logic.

Makefile and task-runner wrappers are deferred by [API Bootstrap Mechanics](20260522-api-bootstrap-mechanics.md).

## Open Questions

- exact `nephos-cli` cluster setup/reset workflow
- backend container image layout and registry
- cross-repository release process between `nephos-api` and `nephos-cli`
