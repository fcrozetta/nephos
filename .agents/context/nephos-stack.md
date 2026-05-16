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

Migrations:

- Simple explicit SQL migrations
- No ORM-driven migration framework is selected for Phase 1

Controller/reconciler:

- API-owned in-process reconciler for Phase 1
- The reconciler must be isolated behind module boundaries so it can later move to a daemon, worker, or in-cluster controller

Kubernetes client:

- Official Python Kubernetes client

CLI/API boundary:

- The CLI talks to the Nephos API/local controller
- The CLI must not become an unstructured direct Kubernetes mutation layer

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

## Still To Decide

Packaging/distribution for the backend and CLI are not fully decided.

Local development workflow should be documented before implementation starts.

Testing defaults should follow the project baseline unless Fer chooses otherwise:

- pytest
- Ruff
- uv
