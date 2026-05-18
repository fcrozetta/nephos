# Nephos Stack

## Repository Boundary

Nephos is split across repositories.

This repository, `nephos`, owns the backend control plane:

- API
- desired-state persistence
- reconciliation orchestration
- catalog and platform model
- architecture context and ADRs

The CLI lives in a separate repository:

- GitHub: `https://github.com/fcrozetta/nephos-cli`
- Local path: `../nephos-cli`

The CLI repository is adjacent to this repository but still needs project setup/configuration.

Setup UX and command implementation belong in the CLI repository after Nephos API `0.0.1` is implemented.

Do not implement CLI code in this repository unless Fer explicitly changes the repository boundary.

## Accepted Phase 1 Stack

Backend language:

- Python

API framework:

- FastAPI

CLI language/framework:

- Python
- Typer
- Implemented in `../nephos-cli`, not this repository

Frontend:

- Deferred for Phase 1
- No frontend framework is selected yet

Persistence:

- SQLite is the canonical Phase 1 desired-state database
- The Nephos API/database is the source of truth for desired platform state
- Platform configuration that affects reconciliation, such as ingress root domains, is stored in the API/database as desired state
- The backend may start with an empty database and report platform configuration as incomplete until setup creates required desired state

Migrations:

- Simple explicit SQL migrations
- No ORM-driven migration framework is selected for Phase 1

Controller/reconciler:

- API-owned in-process reconciler for Phase 1
- The reconciler must be isolated behind module boundaries so it can later move to a daemon, worker, or in-cluster controller

Kubernetes client:

- Official Python Kubernetes client

Local development:

- `uv` is the canonical backend Python workflow
- backend runs as a local process during development
- CLI points at the local backend/API during development

Testing:

- `pytest` for backend tests
- `ruff` for backend linting/formatting checks
- mocks/fakes for backend unit tests
- real K3s for Kubernetes integration tests

Packaging/distribution:

- backend container image for runtime packaging
- full installer packaging deferred
- CLI packaging/test/lint/release workflow lives in `../nephos-cli`

CLI/API boundary:

- The CLI talks to the Nephos API/local controller
- The CLI must not become an unstructured direct Kubernetes mutation layer
- Phase 1 has backend/CLI version awareness but no strict compatibility blocking
- Backend should expose a version endpoint
- CLI should report CLI and backend versions
- CLI may warn on unknown/newer/older backend version
- CLI should not block state-mutating commands solely because of version mismatch in Phase 1

State import/export:

- YAML is import/export only
- YAML is not the canonical source of truth

Deferred architecture:

- Kubernetes CRDs are deferred
- GitOps as source of truth is deferred
- Nephos state backup is deferred to the broader backup model

## Drift Policy

Phase 1 should detect and report drift.

Nephos may reconcile Nephos-owned resources when desired state is explicit, especially during lifecycle operations or explicit reconciliation.

Nephos must not mutate Kubernetes resources it does not own.

Nephos-owned runtime resources should be labeled and/or annotated so drift detection and reconciliation can identify ownership.

Nephos-managed Kubernetes resources should use `app.kubernetes.io/managed-by: nephos`.

Nephos-owned relationship metadata uses `nephos.pro/*` keys.

Nephos does not use Kubernetes `ownerReferences` to represent platform relationships in Phase 1.

## Still To Decide

Exact developer commands are not finalized.

Need to decide:

- exact `uv` commands
- exact local SQLite initialization/reset commands
- exact migration command
- exact K3s startup/reset workflow
- exact integration test markers
- backend image layout and registry
- cross-repo release process
