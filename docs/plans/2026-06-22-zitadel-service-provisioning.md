# Zitadel Service Provisioning Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task if splitting work; otherwise execute sequentially with TDD and small commits.

**Goal:** Make the Nephos Zitadel Service fully usable for dogfood Apps by deploying a bootstrap automation identity and provisioning app-scoped OIDC clients/service-account material through Nephos bindings.

**Architecture:** Keep Zitadel a Nephos Service, not an App. Nephos desired state remains canonical; Pulumi performs internal provider labor through `pulumiverse_zitadel`. Binding reconciliation calls a Nephos-owned Python provisioner that creates Zitadel Projects/OIDC Applications/Machine Users and materializes only redacted summaries plus App-side Kubernetes Secrets.

**Tech Stack:** Python 3.12, FastAPI, SQLite desired state, Kubernetes Python client, Pulumi Automation API, `pulumiverse-zitadel`, ZITADEL v2.58 bootstrap `FirstInstance` machine-key support.

---

## Non-goals

- Do not make Zitadel the Nephos control-plane login in this slice.
- Do not model Chiron or any specific dogfood App here.
- Do not add canonical JSON schemas under `schemas/` or canonical examples under `examples/`.
- Do not add a general user-facing Service operation API.
- Do not expose raw client secrets, machine keys, PATs, or Pulumi stack outputs in API/status payloads.
- Do not rely on the debug Cloudflare tunnel or debug host port-forward for provisioning.

## Current understanding

- Accepted ADRs already define Zitadel as a Service-only alpha backbone provider for `oidc/oidc` and `service-account/jwt`.
- `ZitadelAppScopedProvisioner` exists but currently blocks without a fake test client.
- Binding reconciliation already materializes App-side Secrets and redacts output summaries.
- `BindingProvisioningContext` currently lacks route/domain information; OIDC needs redirect/logout URIs.
- ZITADEL setup supports a first-instance machine identity and writes its machine key to `ZITADEL_FIRSTINSTANCE_MACHINEKEYPATH`.
- The Pulumi provider package is `pulumiverse-zitadel` with Python import `pulumiverse_zitadel`.

## Files likely to change

- `pyproject.toml` / `uv.lock`
- `src/nephos_api/provisioners/base.py`
- `src/nephos_api/provisioners/zitadel.py`
- `src/nephos_api/reconciler.py`
- `src/nephos_api/providers/kubernetes.py`
- `src/nephos_api/dev_backbone.py`
- `src/nephos_api/main.py`
- `tests/test_alpha_backbone_provisioning.py`
- `tests/test_pulumi_kubernetes_provider.py`
- `tests/test_reconciler_runtime.py`
- new focused tests for the Pulumi Zitadel client/program if needed

## Proposed steps

### Task 1: Lock the bootstrap runtime contract

**Objective:** Make the Zitadel runtime create and persist a Nephos-owned bootstrap machine key.

**Steps:**
1. Add failing tests in `tests/test_pulumi_kubernetes_provider.py` asserting the Zitadel container sets:
   - `ZITADEL_FIRSTINSTANCE_MACHINEKEYPATH`
   - `ZITADEL_FIRSTINSTANCE_ORG_MACHINE_MACHINE_USERNAME`
   - `ZITADEL_FIRSTINSTANCE_ORG_MACHINE_MACHINE_NAME`
   - `ZITADEL_FIRSTINSTANCE_ORG_MACHINE_MACHINEKEY_TYPE=1`
2. Assert a persistent `bootstrap` volume claim is mounted into the Zitadel container at a stable path.
3. Add service config options/mappings in `dev_backbone.py` for bootstrap machine username/name/key path if needed, with safe defaults.
4. Implement the Kubernetes provider changes.
5. Verify targeted tests pass.

### Task 2: Extend binding context with route/domain metadata

**Objective:** Give OIDC provisioning enough information to compute default redirect/logout URIs without adding a new public manifest schema.

**Steps:**
1. Extend `BindingProvisioningContext` with optional immutable route/domain fields:
   - `app_routes: tuple[Mapping[str, object], ...] = ()`
   - `platform_domains: tuple[Mapping[str, object], ...] = ()`
2. Update reconciler binding/deprovision context construction.
3. Derive app route/domain metadata from existing private helpers.
4. Preserve existing tests by defaulting fields.
5. Add a focused reconciler test proving an OIDC binding context includes route/domain data.

### Task 3: Define deterministic Zitadel binding outputs

**Objective:** Lock the App-side Secret contract for dogfood Apps.

**OIDC output keys:**

```text
issuerUrl
clientId
clientSecret
redirectUris
postLogoutRedirectUris
authorizationUrl
tokenUrl
jwksUrl
```

**Service-account/JWT output keys:**

```text
issuerUrl
serviceAccountId
keyJson
audience
```

**Steps:**
1. Update `tests/test_alpha_backbone_provisioning.py` to assert these keys.
2. Ensure redacted binding summaries only include key names and never values.
3. Keep `clientSecret`/`keyJson` only in App-side Kubernetes Secrets.

### Task 4: Add the Pulumi Zitadel provisioning client

**Objective:** Replace the blocking live Zitadel client path with a real internal adapter.

**Steps:**
1. Add dependency `pulumiverse-zitadel>=0.2,<1`.
2. Implement a `PulumiZitadelProvisioningClient` behind `ZitadelAppScopedProvisioner`.
3. Use Pulumi local backend under `.nephos/pulumi/state` and workspaces under `.nephos/pulumi/workspaces`.
4. Authenticate with the bootstrap machine key JSON read from the Nephos-owned Zitadel pod/volume.
5. Use an internal temporary port-forward or equivalent Kubernetes API path for provisioning; do not depend on debug Cloudflare/host port-forward.
6. Create/update per-binding Pulumi stacks with stable stack names derived from `binding_id`.
7. Export required output fields from the Pulumi program.
8. Implement destroy/deprovision by destroying the binding stack.

### Task 5: Wire default factory and settings

**Objective:** Make `nephos-api serve` use the real Zitadel provisioner when Pulumi/Kubernetes prerequisites are present.

**Steps:**
1. Update `default_postgres_provisioner_factory` or rename it to a generic backbone provisioner factory in a compatibility-safe way.
2. Keep PostgreSQL, SeaweedFS, ArcadeDB dispatch intact.
3. Pass Kubernetes client/settings/Pulumi base dirs into the Zitadel client.
4. Block with `binding_provisioner_unavailable`, `pulumi_cli_missing`, or `pulumi_passphrase_missing` with clear messages when prerequisites are absent.

### Task 6: Live smoke through Nephos API

**Objective:** Prove a dogfood-style App can bind to Zitadel.

**Steps:**
1. Add a temporary smoke App catalog entry under ignored `.nephos/catalog` with an `oidc/oidc` requirement and route.
2. Install the App through `POST /apps` with binding to `zitadel`.
3. Let the reconciler process the binding.
4. Verify:
   - Zitadel Project exists.
   - Zitadel OIDC App exists.
   - App namespace Secret `nephos-bind-<alias>` contains expected OIDC keys.
   - API binding summary is redacted.
5. Do not commit the temporary smoke catalog entry.

## Risks

- The first-instance machine key is only created on first setup; existing local Zitadel instances may need destroy/reinstall or a one-time migration path.
- Pulumi provider constants may differ from ZITADEL docs; verify against live provider errors.
- Temporary port-forwarding inside the provisioner must be bounded and cleaned up.
- OIDC redirect URI defaults are useful for dogfood but may need a later manifest/config schema for complex Apps.
- Machine key/PAT handling must not leak through logs, status, database summaries, or test output.

## Validation commands

```bash
uv lock --check
uv run ruff check .
uv run pytest tests/test_alpha_backbone_provisioning.py tests/test_pulumi_kubernetes_provider.py tests/test_reconciler_runtime.py -q
uv run pytest -q
git diff --check
```

Live smoke, with explicit local prerequisites:

```bash
export PULUMI_CONFIG_PASSPHRASE=local-dev
export NEPHOS_API_RUN_KUBERNETES_TESTS=1
uv run nephos-api dev backbone-smoke --timeout-seconds 600
```

## Rollback notes

- Runtime bootstrap changes can be reverted independently of the provisioning client.
- If Pulumi Zitadel provider behavior is incompatible, keep the bootstrap machine-key runtime work and revert only the client wiring.
- If route-derived redirect URIs are insufficient, keep context plumbing and add a later accepted manifest/config decision for explicit OIDC callback paths.

## Open questions

- Should explicit OIDC redirect/logout URI configuration live in App config, requirement metadata, or binding config later?
- Should Nephos persist a Service-side Kubernetes Secret containing the bootstrap machine key, or keep reading it from the Zitadel pod/PVC for alpha?
- Should service-account/JWT bindings create a Zitadel Machine User per binding or per App with one key per binding?
