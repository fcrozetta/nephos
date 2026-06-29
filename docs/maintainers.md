# Nephos Maintainer Guide

This document is for people changing the `nephos-api` repository. The top-level
README is for users trying Nephos, so implementation details, verification
habits, and architecture references belong here or in the linked maintainer docs.

## Start here

Read these files before changing behavior or public contracts:

| File or directory | Purpose |
| --- | --- |
| `AGENTS.md` | Product boundaries, lifecycle semantics, architecture write rules, and agent workflow. |
| `PLANS.md` | Current implementation plan, non-goals, validation commands, and open questions. |
| `.agents/context/` | Architecture context that explains the accepted model. |
| `docs/adr/` | Architectural Decision Records. Accepted ADRs are durable. |
| `docs/testing/api-0-0-1-manual.md` | Manual runtime smoke and Kubernetes integration checks. |

## Repository shape

```text
src/nephos_api/
  api/                 FastAPI routers and response shaping
  providers/           Provider interfaces and provider-backed deployers
  migrations/          SQLite migrations
  catalog.py           App/Service catalog loading and validation
  cli.py               Backend-local `nephos-api` commands
  config.py            Environment and `.env` loading
  db.py                SQLite connection and migration helpers
  kubernetes_runtime.py Runtime object helpers for Nephos-owned resources
  main.py              FastAPI app factory and lifespan wiring
  provisioning.py      App-scoped Service provisioning handlers
  reconciler.py        Desired-state reconciliation engine
  repository.py        SQLite desired-state repository

tests/                 Unit, API, packaging, provider, and opt-in Kubernetes tests
docs/adr/              Architecture decisions
docs/testing/          Manual and runtime verification notes
```

## Development workflow

1. Start from a clean branch and inspect current state:

   ```bash
   git status --short --branch
   git log --oneline --decorate -8
   ```

2. For multi-step implementation work, update `PLANS.md` before editing code.

3. Keep changes behavior-preserving unless the plan and ADR/context documents
   already authorize a behavior or contract change.

4. Use temporary state for manual checks:

   ```bash
   TMP=$(mktemp -d /tmp/nephos-api.XXXXXX)
   NEPHOS_API_DB_PATH="$TMP/state/nephos.db" \
   NEPHOS_API_INTERNAL_DOMAIN=nephos.localhost \
     uv run nephos-api init
   ```

5. Do not manage cluster lifecycle from this repository. Nephos may target a
   selected Kubernetes context, but cluster creation/destruction stays external.

## Verification

Run the fast baseline before and after substantial changes:

```bash
uv lock --check
uv run ruff check .
uv run pytest -q
git diff --check
```

For API/server smoke checks with a temp database:

```bash
TMP=$(mktemp -d /tmp/nephos-api-serve.XXXXXX)
NEPHOS_API_DB_PATH="$TMP/state/nephos.db" \
NEPHOS_API_INTERNAL_DOMAIN=nephos.localhost \
  uv run nephos-api serve --port 8765
```

Then, from another terminal:

```bash
curl -fsS http://127.0.0.1:8765/version
curl -fsS http://127.0.0.1:8765/healthz
```

Kubernetes integration tests are opt-in only:

```bash
NEPHOS_API_RUN_KUBERNETES_TESTS=1 \
PULUMI_CONFIG_PASSPHRASE=<local-test-passphrase> \
  uv run pytest tests/test_kubernetes_runtime_integration.py -m kubernetes -q
```

## Code simplification rules

Prefer small, behavior-preserving refactors that make contracts clearer:

- Preserve exact Nephos error codes, status codes, and response fields unless a
  public contract change is explicitly planned.
- Keep FastAPI handlers at the desired-state boundary; handlers record intent,
  while the reconciler and providers touch runtime state.
- Keep repository helpers explicit about table names and lifecycle semantics.
- Do not mix API/resource cleanup with reconciler/runtime/provider architecture
  changes unless the plan says so.
- Add tests or run targeted existing tests for any branch that affects lifecycle,
  binding-provider selection, catalog validation, status snapshots, or runtime
  cleanup.

## Comment style

Use comments to protect non-obvious product contracts, not to narrate obvious
Python. Prefer Better Comments prefixes so warnings and invariants stand out in
editors that support the extension:

| Prefix | Use for |
| --- | --- |
| `# !` | Invariants, safety rules, API error precedence, secret-handling warnings. |
| `# *` | Important flow markers where a short highlight prevents mis-editing. |
| `# ?` | Genuine open questions that should become a plan item or ADR note if they affect behavior. |
| `# TODO` | Concrete follow-up work that is intentionally deferred and easy to search. |

Examples:

```python
# ! Error precedence is part of the API contract; keep this before selection.
_reject_unknown_binding_aliases(selections, requirements)

# * Shared install preflight: resolve catalog identity before mutating state.
catalog_entry, slug, source_path = _install_catalog_entry(...)
```

## Documentation boundaries

Keep the documentation split by audience:

- `README.md`: user-facing overview, quick start, API usage, limitations.
- `docs/maintainers.md`: contributor workflow, repository structure, verification,
  code/comment conventions.
- `docs/testing/`: manual and runtime verification recipes.
- `.agents/context/` and `docs/adr/`: architecture context and decisions.

When a change affects architecture structure, lifecycle semantics, source of
truth, manifest/schema shape, runtime boundaries, auth/security, backup/data
lifecycle, public API/CLI contracts, or catalog behavior, update the relevant
ADR/context/open-question documents as required by `AGENTS.md`.

## Release readiness notes

Before presenting a branch as ready:

1. Re-run the baseline verification commands.
2. Review `git diff --stat` and `git diff --check`.
3. Confirm generated state such as `.nephos/`, `.pytest_cache/`, `.ruff_cache/`,
   `dist/`, and virtualenv files are not part of the commit.
4. If the change affects shipped CLI paths, repeat an installed-wheel smoke in a
   fresh virtual environment.
5. If the change affects public PR or issue text, scan for tokens, private paths,
   local domains, and operational details before posting.
