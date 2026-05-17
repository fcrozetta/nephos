# Nephos Open Questions

## Namespace Strategy

Question:

What namespace model should Nephos use?

Current leaning:

- one namespace per App
- one namespace per Service
- reserved nephos-system namespace for Nephos control plane

## Manifest Schema Details

Question:

What are the concrete App and Service manifest schemas?

Accepted direction:

- separate App and Service Nephos manifest formats
- Helm-primary runtime deployment references
- raw Kubernetes manifest fallback
- no schema file until Fer approves the shape

Need to decide:

- exact field names
- manifest filenames
- versioning scheme
- required vs optional fields
- config surface format
- capability requirement syntax
- exposed capability syntax
- runtime deployment reference syntax
- validation rules

## Dedicated Service Sharing Policy Details

Question:

How should explicit sharing of dedicated Service instances work?

Accepted direction:

- dedicated Service instances are created because an App requests or requires isolation
- dedicated Service instances remain first-class Services
- other Apps may explicitly bind to a dedicated Service instance for integration
- Phase 1 reserves the concept and supports shared/global Service instances first

Need to decide:

- whether a dedicated Service instance has an owning/initiating App field
- whether explicit sharing requires owner confirmation
- whether dedicated instances advertise capabilities normally or behind a sharing flag
- whether default provider selection may choose a dedicated instance
- how backup/restore lifecycle works when several Apps bind to a dedicated instance
- how destroy impact lists represent initiating App vs later dependents

## Service Operation Contract

Question:

What is the concrete contract for Service operations?

Accepted direction:

- Service operation is the canonical term
- Service management action is only a descriptive phrase
- Service operations are optional in Phase 1
- Service operations must be backend/API-owned and typed
- Service operations must not be arbitrary user-facing shell scripts

Need to decide:

- operation declaration format
- input/output schema
- execution model
- audit/status model
- permissions and safety prompts
- idempotency expectations
- relationship to binding lifecycle
- relationship to backup/restore lifecycle

## Catalog Source and Trust Beyond Phase 1

Question:

How should non-local catalogs work after Phase 1?

Accepted Phase 1 direction:

- local filesystem catalog first

Deferred:

- Git repositories
- OCI artifacts or registries
- remote indexes
- signed catalogs
- private remote catalogs

Need to decide:

- trust model
- signing/verifying catalog entries
- private catalog credentials
- catalog versioning
- catalog update behavior
- how catalog metadata relates to package manifests

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
