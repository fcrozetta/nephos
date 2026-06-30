# 1Password Connect LCL Service Slice

## Goal

Add the first Nephos-managed LCL `onepassword-connect` Service path so local
Nephos can install a Connect API/sync runtime from operator-owned bootstrap
material without storing resolved 1Password values in desired state.

## Non-goals

- Do not deploy the 1Password Kubernetes Operator in this slice.
- Do not implement app-scoped secret materialization from Connect yet.
- Do not change `dev` or `prd` token/service-account policy.
- Do not create or rotate real Connect credentials automatically.
- Do not replace the existing `op://...` CLI resolver yet.

## Current understanding

- `nephos-lcl` remains the LCL source of truth.
- The placeholder item `onepassword-connect-lcl` is reserved for future Connect
  credentials and token fields.
- Nephos desired state should carry `op://...` refs; the runtime provider should
  resolve them only while materializing Kubernetes resources.
- Connect itself needs the Connect credentials JSON file; clients/operators use a
  Connect token.

## Files likely to change

Nephos API repo:

- `PLANS.md`
- `src/nephos_api/main.py`
- `src/nephos_api/providers/kubernetes.py`
- `tests/test_main.py`
- `tests/test_pulumi_kubernetes_provider.py`

Core registry repo:

- `services/onepassword-connect/service.yaml`
- `services/onepassword-connect/README.md`
- `scripts/validate_catalog.py`

## Proposed steps

1. Add a `onepassword-connect` core Service catalog entry with explicit LCL
   credentials/token config refs.
2. Add a Pulumi Kubernetes workload renderer for a local Connect API/sync
   Deployment, Service, and Secret.
3. Wire the provider runtime name into the default Service provider router.
4. Add focused unit/catalog tests.
5. Validate Nephos and core-registry catalog loading.

## Risks

- Confusing the Connect server credentials JSON with the Connect client token.
- Logging or committing resolved credentials/token values.
- Treating Connect deployment as the same as Kubernetes Operator-backed workload
  Secret materialization; that remains a later slice.
- Using broad tokens beyond `nephos-lcl` in local testing.

## Validation commands

```bash
uv run ruff check src/nephos_api/main.py src/nephos_api/providers/kubernetes.py tests/test_main.py tests/test_pulumi_kubernetes_provider.py
uv run pytest tests/test_main.py tests/test_pulumi_kubernetes_provider.py -q
(cd .nephos/registries/core-registry && NEPHOS_SRC=<nephos-src>/src python3 scripts/validate_catalog.py)
uv run ruff check .
uv run pytest -q
git diff --check
```

## Rollback notes

- Revert the API runtime provider and core-registry catalog entry.
- Do not delete or rotate 1Password Connect credentials as part of repository
  rollback unless explicitly requested.

## Open questions

- Whether the later Operator slice should deploy via Helm chart or explicit
  Kubernetes manifests.
- Exact Connect token rotation and storage policy for `dev`/`prd`.
- Whether Nephos should support both service-account and Connect-backed secret
  providers behind the same `secrets/onepassword` capability.
