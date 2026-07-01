# ZITADEL Admin Password Complexity Plan

> **For Hermes:** Implement this as a narrow runtime preflight with focused tests.

**Goal:** Block ZITADEL runtimes before Kubernetes reconciliation when the configured admin password cannot satisfy ZITADEL's default bootstrap complexity policy.

**Architecture:** Keep validation at the Pulumi Kubernetes workload boundary where resolved runtime values are available. Raise `RuntimeBlockedError` so the existing reconciler records a blocked status instead of allowing ZITADEL to CrashLoop during `start-from-init`.

**Tech Stack:** Python, Nephos Pulumi Kubernetes provider, pytest.

---

## Non-goals

- Do not discover custom ZITADEL password policies.
- Do not implement Pulumi lock or partial-bootstrap repair.
- Do not change public catalog schemas.
- Do not print or expose secret values in API/status/log output.

## Current understanding

- A local smoke reached ZITADEL runtime but failed during `03_default_instance` with `Errors.User.PasswordComplexityPolicy.HasSymbol`.
- Nephos already maps resolved `adminPassword` into the ZITADEL Kubernetes Secret and reconciler already converts `RuntimeBlockedError` into blocked status evidence.
- The narrow fix is to fail before rendering runtime resources when `adminPassword` lacks the default complexity shape.

## Files likely to change

- `src/nephos_api/providers/kubernetes.py`
- `tests/test_pulumi_kubernetes_provider.py`

## Proposed steps

1. Add a `_validate_zitadel_admin_password` helper that requires at least 8 characters, lowercase, uppercase, digit, and symbol.
2. Call it immediately after reading `adminPassword` in `_zitadel_service`.
3. Add a regression test for a password without a symbol returning `runtime_config_invalid`.
4. Update existing ZITADEL provider tests to use complexity-compliant placeholder passwords.

## Risks

- This only models the default policy. Custom ZITADEL policies remain out of scope.
- Blocking digest or secret-ref-like unresolved values would be wrong, but provider inputs are resolved runtime values at this boundary.

## Validation commands

- `uv run pytest -q tests/test_pulumi_kubernetes_provider.py`
- `uv run ruff check .`
- `uv run pytest -q`
- `git diff --check`

## Rollback notes

- Revert the provider helper/call and test updates to return to runtime-only failure behavior.

## Open questions

- None for this slice.
