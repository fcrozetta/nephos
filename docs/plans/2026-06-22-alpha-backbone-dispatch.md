# Nephos Alpha Backbone Dispatch Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task. Dispatch only after the architecture decision task is complete or explicitly accepted by Fer.

**Goal:** Turn Nephos from API/runtime proof into a usable local alpha backbone that can install PostgreSQL, Zitadel, SeaweedFS, and ArcadeDB, then prove app-local connections through Nephos bindings.

**Architecture:** Nephos remains the desired-state platform. Pulumi is the runtime labor backend. Helm is allowed only underneath Pulumi-backed Service providers when it is the easiest way to install a Service; Helm charts do not define Nephos Service behavior. Service providers expose typed install/lifecycle/status/binding actions.

**Tech Stack:** FastAPI, SQLite, Pydantic catalog validation, Kubernetes Python client, Pulumi Automation API, Pulumi Kubernetes provider, optional Helm releases through Pulumi, pytest.

---

## Architecture Notice Before Editing ADR/Context

This work changes catalog behavior, manifest shape, auth/security bootstrap, Service binding semantics, and Phase 1 scope. Before any agent changes `.agents/context/` or `docs/adr/`, tell Fer explicitly that these files need updates and why:

- `docs/adr/20260622-alpha-backbone-catalog-and-service-providers.md` — new ADR to accept protocol-aware capabilities, the alpha backbone catalog order, Zitadel-as-Service-with-surfaces, Pulumi-first runtime, and Helm-as-implementation-detail.
- `.agents/context/nephos-catalog-loading.md` — update catalog summaries and validation to include protocol-aware App requirements and Service provisions.
- `.agents/context/nephos-reconciliation.md` — update binding reconciliation to select by `capability + protocol` and call typed provider provisioning actions.
- `.agents/context/nephos-auth.md` — update Zitadel as the first auth Service and define per-App OIDC/service-account provisioning boundaries.
- `.agents/context/nephos-phase1.md` and `.agents/context/nephos-open-questions.md` — record the alpha backbone as Phase 1 scope and move unresolved details to open questions.

Do not modify those architecture files silently. If Fer wants implementation to proceed before docs are accepted, create a draft ADR and keep canonical schema/example changes out of `schemas/` and `examples/`.

## Dispatch Order

### Wave 0 — Decision and scope lock

Run first, single agent:

1. Draft/patch the ADR and context docs listed above.
2. Keep the decision focused: no Aspire, Pulumi-first, Helm optional under provider code, Zitadel is a Service with surfaces, DB matching is `capability + protocol`.
3. Commit docs separately after review.

### Wave 1 — Parallel code preparation

After Wave 0:

- Agent A: `2026-06-22-protocol-aware-capability-matching.md`
- Agent B: `2026-06-22-core-service-runtime-providers.md`

These can run in parallel if both start from the accepted ADR. Agent B must not promote canonical catalog entries until Agent A lands the manifest support.

### Wave 2 — Binding providers

After Agent A lands protocol-aware bindings and Agent B lands at least service install/status stubs:

- Agent C: `2026-06-22-core-service-binding-provisioners.md`

### Wave 3 — End-to-end proof

After Wave 2:

- Agent D: `2026-06-22-alpha-local-backbone-smoke.md`

## Definition of Done

- Catalog manifests can express `capability + protocol` for App requirements and Service provisions.
- PostgreSQL provides `sql/postgres` and provisions app-scoped database credentials.
- Zitadel is modeled only as a Service and exposes admin/login surfaces; it provisions per-App OIDC clients and service-account material when requested.
- SeaweedFS provides `object-storage/s3` and provisions app-scoped bucket/access credentials.
- ArcadeDB provides `sql/arcadedb`, `opencypher/bolt`, `opencypher/n4j`, optional `gremlin/gremlin`, and optional `mongo/mongo` when enabled.
- Nephos can install the four backbone Services locally through API desired state and reconciler requests.
- A local smoke proves app connection materialization through Nephos binding Secrets without exposing raw secret values in API/status/logs.

## Non-goals

- Do not add Aspire.
- Do not expose Pulumi or Helm as the user-facing product model.
- Do not build the final marketplace/community registry.
- Do not build a full Console.
- Do not implement global backup/restore framework in this batch.
- Do not manage cluster lifecycle from this repository.
- Do not commit generated `.nephos/`, Pulumi workspaces, or cluster artifacts.

## Shared Validation Commands

Run after each implementation slice unless the slice is docs-only:

```bash
uv lock --check
uv run ruff check .
uv run pytest -q
git diff --check
```

For live runtime slices, only when a disposable local cluster is selected:

```bash
PULUMI_CONFIG_PASSPHRASE=local-dev \
NEPHOS_API_RUN_KUBERNETES_TESTS=1 \
  uv run pytest tests/test_kubernetes_runtime_integration.py -m kubernetes -q
```

For final alpha proof:

```bash
PULUMI_CONFIG_PASSPHRASE=local-dev uv run nephos-api dev backbone-smoke --timeout-seconds 600
```

## Rollback Notes

- Architecture docs and ADRs should be reverted separately from implementation.
- Runtime provider changes should remain behind `src/nephos_api/providers/` so reverting a Service provider does not alter API desired-state semantics.
- If a live smoke leaves resources behind, clean only Nephos-owned namespaces with accepted labels.
