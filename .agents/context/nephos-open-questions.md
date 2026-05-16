# Nephos Open Questions

## App Package Format

Question:

What format defines installable Apps?

Candidates:

- nephos.yml
- Helm chart wrapper
- catalog entry referencing Helm/manifests
- OCI artifact

Need to define schema.

## Namespace Strategy

Question:

What namespace model should Nephos use?

Current leaning:

- one namespace per App
- one namespace per Service
- reserved nephos-system namespace for Nephos control plane

## Backend and CLI Packaging

Question:

How should the backend and CLI be packaged and distributed?

Current accepted repository boundary:

- backend/control plane lives in `nephos`
- CLI lives in `../nephos-cli`

Need to decide:

- backend package layout
- backend container image strategy
- CLI installation path
- version compatibility between backend and CLI
- release process across the two repositories

## Local Development Workflow

Question:

What is the canonical local development workflow for Nephos?

Need to decide:

- whether local backend development uses `uv`
- how SQLite state is initialized/reset
- how K3s is started for local development
- whether Docker Compose is used for supporting developer services
- how `../nephos-cli` points to a local backend

## Testing Approach

Question:

What is the required testing baseline before implementation starts?

Current default from Fer's ecosystem:

- pytest
- Ruff
- uv

Need to decide:

- unit vs integration test boundaries
- whether Kubernetes integration tests use K3s, kind, or mocks
- whether CLI tests live only in `../nephos-cli`
