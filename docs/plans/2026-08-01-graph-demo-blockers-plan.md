# graph-demo Platform Blockers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the five platform defects that stopped a third-party App from installing, signing in, or being deleted.

**Architecture:** Two independent increments. **A** gives the binding-provisioning path the portal-derived Service identity the deploy path already has, which unblocks OIDC and closes issue #61 in the same move. **B** makes teardown tolerate a failing provisioner and implements the capped retry ADR 20260518 called for and deferred.

**Tech Stack:** Python 3.12+, FastAPI, SQLite, pytest, ruff. `uv` for everything.

## Global Constraints

- Design doc: `docs/plans/2026-08-01-graph-demo-blockers-design.md`. Read it if a task's intent is unclear.
- Branch `fix/graph-demo-blockers`, off `main` at `4766a94`. Commit per task. Do not push; do not open a PR without being asked.
- `uv run pytest` and `uv run ruff check . && uv run ruff format --check .` must be green before every commit. The suite is large; run it once per task before committing, not after every edit.
- Repo test style: plain `test_<behaviour>` names, module-level `_helper()` factories, direct asserts, no docstrings on tests. Match the file you are editing.
- Ruff: `line-length = 88`, `select = ["E", "F", "I", "UP", "B", "SIM"]`, `target-version = "py312"`.
> **Scope changed 2026-08-01 (later the same day).** Fer asked for the
> ArcadeDB half to work, so the `opencypher` engine *was* built and is in
> this branch (`provisioners/arcadedb_client.py`, registered in
> `main._build_provisioning_engines`). Recorded here because the text below
> says the opposite and AGENTS.md requires the record to change with the
> code.

> **Also dropped 2026-08-01:** the capped retry for blocked reconciliation
> requests. Review found it contradicts ADR 20260518 ("Blocked requests
> require desired-state changes, user input, or explicit manual
> reconciliation"), made every historical blocked row retry-eligible at
> once on upgrade, and did not honour its own cap. It also fixed nothing:
> destroy completing first time was the teardown guards, not the retry.

- **Out of scope: building an `opencypher` provisioning engine.** The `graph` binding is expected to keep blocking with `provisioning_engine_unknown` after every task here. That is correct, not a regression.
- Do not modify `~/projects/core-registry` or `~/projects/nephos-graph-demo`.

---

## File Structure

**Increment A**

| File | Responsibility |
|---|---|
| `src/nephos_api/routing.py` | **Modify.** Gains `ServicePortalIdentity` and `service_portal_identity()`. This module already owns host and URL derivation for portals, so the new derivation belongs here rather than in the provisioner layer — and putting it here keeps one home for the `PLATFORM_ROUTE_*` constants it depends on. Also loses the now-stale warning comment about `_route_scheme`. |
| `src/nephos_api/provisioners/base.py` | **Modify.** `BindingProvisioningContext` gains one optional `service_portal` field. |
| `src/nephos_api/reconciler.py` | **Modify.** New `_service_portal_identity(slug)` helper; three context construction sites populate the field. |
| `src/nephos_api/providers/deployer.py` | **Modify.** The service-dependency construction site populates the field. |
| `src/nephos_api/provisioners/zitadel.py` | **Modify.** `_provisioning_domain`/`_port`/`_secure` read portal-first; `_route_base_urls` stops guessing scheme; `_route_scheme` deleted. |
| `tests/test_routing.py` | **Create.** Pure unit tests for the new derivation. |
| `tests/test_zitadel_provisioning_identity.py` | **Create.** Portal-first, config fallback, block-with-neither, and the `http` scheme regression. |
| `docs/adr/20260726-service-portals.md` | **Modify.** Dated addendum. |

**Increment B**

| File | Responsibility |
|---|---|
| `src/nephos_api/provisioners/registry.py` | **Modify.** Teardown tolerates an unresolvable engine. |
| `src/nephos_api/reconciler.py` | **Modify.** App teardown guarded; blocked requests increment attempts and carry an attempt suffix. |
| `src/nephos_api/migrations/0005_add_reconciliation_attempts.sql` | **Create.** |
| `src/nephos_api/db.py` | **Modify.** `utc_now_minus()` beside `utc_now()`, so the timestamp format has one home. |
| `src/nephos_api/repository.py` | **Modify.** Retry constants; claim query; attempts increment. |
| `tests/test_reconciliation_retry.py` | **Create.** Retry eligibility, cap, ordering. |
| `docs/adr/20260518-reconciliation-execution-model.md` | **Modify.** Dated addendum. |

---

## Task 1: Portal identity derivation

**Files:**
- Modify: `src/nephos_api/routing.py`
- Test: `tests/test_routing.py` (create)

**Interfaces:**
- Consumes: existing `portal_canonical_domain`, `service_portal_host`, `PLATFORM_ROUTE_PORT`, `PLATFORM_ROUTE_SECURE`, `RootDomain`.
- Produces: `ServicePortalIdentity(host: str, port: int, secure: bool)` and `service_portal_identity(*, service_slug: str, first_portal_name: str | None, domains: Sequence[RootDomain]) -> ServicePortalIdentity | None`.

- [ ] **Step 1: Write the failing tests**

`tests/test_routing.py`:

```python
from dataclasses import dataclass

from nephos_api.routing import (
    ServicePortalIdentity,
    service_portal_identity,
)


@dataclass(frozen=True)
class _Domain:
    domain: str
    is_default: bool = False
    allows_service_portals: bool = False


def _identity(first_portal_name="console", domains=None):
    return service_portal_identity(
        service_slug="auth",
        first_portal_name=first_portal_name,
        domains=domains
        if domains is not None
        else [_Domain("nephos.lcl", is_default=True, allows_service_portals=True)],
    )


def test_identity_uses_the_bare_host_of_the_first_portal():
    assert _identity() == ServicePortalIdentity(
        host="auth.nephos.lcl", port=80, secure=False
    )


def test_identity_is_none_when_the_service_declares_no_portal():
    assert _identity(first_portal_name=None) is None


def test_identity_is_none_when_no_domain_allows_portals():
    domains = [_Domain("nephos.lcl", is_default=True, allows_service_portals=False)]
    assert _identity(domains=domains) is None


def test_identity_falls_back_to_the_first_eligible_non_default_domain():
    domains = [
        _Domain("public.example", is_default=True, allows_service_portals=False),
        _Domain("nephos.lcl", allows_service_portals=True),
    ]
    assert _identity(domains=domains).host == "auth.nephos.lcl"


def test_identity_is_never_https_on_a_lcl_domain():
    # Issue #61: the platform serves generated routes over http. A provisioner
    # that guesses https from the suffix produces an issuer nothing serves.
    identity = _identity()
    assert identity.secure is False
    assert identity.port == 80
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest tests/test_routing.py -q
```

Expected: `ImportError: cannot import name 'ServicePortalIdentity'`.

- [ ] **Step 3: Implement**

In `src/nephos_api/routing.py`, add `from dataclasses import dataclass` and `Sequence` to the existing imports, then append:

```python
@dataclass(frozen=True)
class ServicePortalIdentity:
    """A Service's canonical external address, derived from its first portal.

    The identity a provisioner needs when it configures a Service to know its
    own address — Zitadel's OIDC issuer is exactly this. The deploy path already
    feeds the same value through a `kind: portal` runtime mapping; this is the
    provisioning path's equivalent, so the two cannot disagree.
    """

    host: str
    port: int
    secure: bool


def service_portal_identity(
    *,
    service_slug: str,
    first_portal_name: str | None,
    domains: Sequence[RootDomain],
) -> ServicePortalIdentity | None:
    """The Service's external identity, or None when it has no published one.

    The **first** portal, matching `service_portal_host_prefix`: the first
    portal takes the bare `<service-slug>.<domain>` host, which is what makes
    installing Zitadel under the slug `auth` produce the issuer `auth.<domain>`.
    A later portal is prefixed and is therefore never the Service's identity.

    None is a legitimate answer, not an error: a Service may declare no portal
    at all, and a fresh install has no portal-eligible domain until an operator
    opts one in. The caller decides what to do about it.
    """
    if first_portal_name is None:
        return None
    domain = portal_canonical_domain(domains)
    if domain is None:
        return None
    return ServicePortalIdentity(
        host=service_portal_host(
            service_slug=service_slug,
            portal_name=first_portal_name,
            domain=domain.domain,
            is_first_portal=True,
        ),
        port=PLATFORM_ROUTE_PORT,
        secure=PLATFORM_ROUTE_SECURE,
    )
```

- [ ] **Step 4: Run to verify it passes**

```bash
uv run pytest tests/test_routing.py -q
```

Expected: 5 passed.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest -q
```

```bash
git add src/nephos_api/routing.py tests/test_routing.py
git commit -m "feat(routing): derive a Service's external identity from its first portal"
```

---

## Task 2: Thread portal identity through the provisioning context

**Files:**
- Modify: `src/nephos_api/provisioners/base.py`
- Modify: `src/nephos_api/reconciler.py`
- Modify: `src/nephos_api/providers/deployer.py`
- Test: `tests/test_engine_routing_provisioner.py` (extend)

**Interfaces:**
- Consumes: `ServicePortalIdentity`, `service_portal_identity` (Task 1).
- Produces: `BindingProvisioningContext.service_portal: ServicePortalIdentity | None`, defaulting to `None`; `Reconciler._service_portal_identity(slug: str) -> ServicePortalIdentity | None`.

- [ ] **Step 1: Add the context field**

In `src/nephos_api/provisioners/base.py`, import the type and add the field after `provisioning_engine`:

```python
from nephos_api.routing import ServicePortalIdentity
```

```python
    # The provider Service's own external identity, derived from its first
    # portal (ADR 20260726). A provisioner that configures a Service to know its
    # own address reads this rather than Service config: the config options this
    # replaced were removed when portals landed, and reading them left every
    # OIDC binding blocked. None when the Service publishes no portal.
    service_portal: ServicePortalIdentity | None = None
```

Optional with a default, so every existing construction site and test factory keeps working untouched.

- [ ] **Step 2: Add the reconciler helper**

In `src/nephos_api/reconciler.py`, beside `_service_provisioning_engine`:

```python
    def _service_portal_identity(self, slug: str) -> ServicePortalIdentity | None:
        """The Service's portal-derived external identity, or None."""
        row = self._repository.get_service_row(slug)
        if row is None:
            return None
        source_path = Path(str(row["catalog_source_path"]))
        if not source_path.exists():
            return None
        manifest = ServiceManifest.model_validate(
            yaml.safe_load(source_path.read_text())
        )
        portals = manifest.spec.portals
        return service_portal_identity(
            service_slug=slug,
            first_portal_name=portals[0].name if portals else None,
            domains=self._repository.list_platform_domains(),
        )
```

Add `service_portal_identity` and `ServicePortalIdentity` to the existing `from nephos_api.routing import ...`.

- [ ] **Step 3: Populate all three reconciler construction sites**

At `reconciler.py` lines ~815, ~847, and ~988 — the `BindingProvisioningContext(...)` calls in `_deprovision_app_bindings`, `_cleanup_service_dependent_bindings`, and the binding reconcile — add as the last keyword argument in each:

```python
                    service_portal=self._service_portal_identity(
                        str(binding["service_instance_slug"])
                    ),
```

In `_cleanup_service_dependent_bindings` the local is `context`'s source binding, same expression. Match the surrounding variable name in each site rather than copying blindly.

- [ ] **Step 4: Populate the deployer construction site**

In `src/nephos_api/providers/deployer.py`, in the `BindingProvisioningContext(...)` at line ~343, add:

```python
                    service_portal=self._provider_portal_identity(provider_row),
```

and add the helper beside `_provider_provisioning_engine`:

```python
    def _provider_portal_identity(
        self,
        provider_row: dict[str, object],
    ) -> ServicePortalIdentity | None:
        manifest = _manifest_from_path(
            target_type="service_instance",
            path=Path(str(provider_row["catalog_source_path"])),
        )
        if not isinstance(manifest, ServiceManifest):
            return None
        portals = manifest.spec.portals
        return service_portal_identity(
            service_slug=str(provider_row["slug"]),
            first_portal_name=portals[0].name if portals else None,
            domains=self._repository.list_platform_domains(),
        )
```

Import `ServicePortalIdentity` and `service_portal_identity` from `nephos_api.routing`.

- [ ] **Step 5: Pin that the field survives routing**

Append to `tests/test_engine_routing_provisioner.py`:

```python
def test_routing_preserves_the_service_portal_identity():
    from nephos_api.routing import ServicePortalIdentity

    identity = ServicePortalIdentity(host="auth.nephos.lcl", port=80, secure=False)
    engine = _Recorder({"uri": "x"})
    context = BindingProvisioningContext(
        binding_id="b1",
        app_slug="app",
        service_slug="auth",
        alias="auth",
        capability="oidc",
        protocol="oidc",
        provisioning_engine="oidc",
        service_portal=identity,
    )

    EngineRoutingBindingProvisioner({"oidc": engine}).provision_binding(context)

    assert engine.provisioned[0].service_portal == identity
```

- [ ] **Step 6: Run the full suite**

```bash
uv run pytest -q
```

Expected: all green. A failure here means an existing test constructs the context positionally — fix by keyword, not by reordering the dataclass.

- [ ] **Step 7: Lint and commit**

```bash
uv run ruff check . && uv run ruff format --check .
```

```bash
git add -A && git commit -m "feat(provisioning): carry the provider Service's portal identity on the binding context"
```

---

## Task 3: Zitadel provisions against the portal host

**Files:**
- Modify: `src/nephos_api/provisioners/zitadel.py`
- Test: `tests/test_zitadel_provisioning_identity.py` (create)

**Interfaces:**
- Consumes: `BindingProvisioningContext.service_portal` (Task 2).
- Produces: no new public names. `_provisioning_domain`, `_provisioning_port`, `_provisioning_secure` change source of truth.

- [ ] **Step 1: Write the failing tests**

`tests/test_zitadel_provisioning_identity.py`:

```python
import pytest

from nephos_api.provisioners.base import BindingProvisioningContext
from nephos_api.provisioners.zitadel import (
    _issuer_url,
    _provisioning_domain,
    _provisioning_port,
    _provisioning_secure,
)
from nephos_api.routing import ServicePortalIdentity
from nephos_api.runtime_errors import RuntimeBlockedError

PORTAL = ServicePortalIdentity(host="auth.nephos.lcl", port=80, secure=False)


def _ctx(service_portal=None, service_config=None):
    return BindingProvisioningContext(
        binding_id="b1",
        app_slug="graph-demo",
        service_slug="auth",
        alias="auth",
        capability="oidc",
        protocol="oidc",
        service_config=service_config or {},
        service_portal=service_portal,
    )


def test_domain_prefers_the_portal_identity():
    context = _ctx(
        service_portal=PORTAL,
        service_config={"external-host": "stale.example"},
    )

    assert _provisioning_domain(context) == "auth.nephos.lcl"


def test_domain_falls_back_to_config_when_there_is_no_portal():
    context = _ctx(service_config={"external-host": "legacy.example"})

    assert _provisioning_domain(context) == "legacy.example"


def test_domain_blocks_when_neither_source_exists():
    with pytest.raises(RuntimeBlockedError) as excinfo:
        _provisioning_domain(_ctx())

    assert excinfo.value.reason == "binding_provisioner_unavailable"
    assert "portal" in str(excinfo.value)
    assert "external-host" in str(excinfo.value)


def test_port_and_secure_follow_the_portal():
    context = _ctx(service_portal=PORTAL)

    assert _provisioning_port(context) == 80
    assert _provisioning_secure(context) is False


def test_issuer_url_is_http_without_a_port_suffix_on_a_portal_identity():
    # Issue #61: the platform serves generated routes over http. An https issuer
    # here disagrees with the host Zitadel is actually reachable at.
    assert _issuer_url(_ctx(service_portal=PORTAL)) == "http://auth.nephos.lcl"
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest tests/test_zitadel_provisioning_identity.py -q
```

Expected: `test_domain_prefers_the_portal_identity` fails — the current code reads config and finds `stale.example`.

- [ ] **Step 3: Implement**

Replace the three functions in `src/nephos_api/provisioners/zitadel.py`:

```python
def _provisioning_domain(context: BindingProvisioningContext) -> str:
    """The host Zitadel is reachable at, for provisioning (ADR 20260726).

    Portal-derived first. A Service's external identity is its portal host, and
    the deploy path already feeds Zitadel that same value as `externalHost`.
    Reading it from Service config was left behind when portals landed: once
    core-registry dropped the option, every OIDC binding blocked here.

    The config fallback stays for a non-core Service that still declares
    `external-host`.
    """
    if context.service_portal is not None:
        return context.service_portal.host
    config = context.service_config or {}
    if "external-host" in config or "externalHost" in config:
        return str(_config_value(context, "external-host", "externalHost"))
    raise RuntimeBlockedError(
        reason="binding_provisioner_unavailable",
        message=(
            "Zitadel has no provisioning host: the Service publishes no portal "
            "on a portal-eligible domain, and its config carries no "
            "external-host."
        ),
    )


def _provisioning_port(context: BindingProvisioningContext) -> int:
    if context.service_portal is not None:
        return context.service_portal.port
    return int(
        str(_config_value(context, "external-port", "externalPort", default=443))
    )


def _provisioning_secure(context: BindingProvisioningContext) -> bool:
    if context.service_portal is not None:
        return context.service_portal.secure
    return _bool_config_value(
        context,
        "external-secure",
        "externalSecure",
        default=True,
    )
```

- [ ] **Step 4: Run to verify it passes**

```bash
uv run pytest tests/test_zitadel_provisioning_identity.py -q
```

Expected: 5 passed.

- [ ] **Step 5: Full suite, lint, commit**

```bash
uv run pytest -q && uv run ruff check . && uv run ruff format --check .
```

```bash
git add -A && git commit -m "fix(zitadel): provision against the portal host, not removed Service config"
```

---

## Task 4: App redirect URIs stop guessing https (issue #61)

**Files:**
- Modify: `src/nephos_api/provisioners/zitadel.py`
- Modify: `src/nephos_api/routing.py`
- Test: `tests/test_zitadel_provisioning_identity.py` (extend)

**Interfaces:**
- Consumes: `routing.PLATFORM_ROUTE_SCHEME`.
- Produces: `_route_scheme` is deleted. Any caller outside `_route_base_urls` is a bug — grep before deleting.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_zitadel_provisioning_identity.py`:

```python
from nephos_api.provisioners.zitadel import _oidc_uris


def _route_ctx(domain="nephos.lcl"):
    return BindingProvisioningContext(
        binding_id="b1",
        app_slug="graph-demo",
        service_slug="auth",
        alias="auth",
        capability="oidc",
        protocol="oidc",
        app_routes=({"name": "web"},),
        platform_domains=({"domain": domain, "default": True},),
    )


def test_redirect_uris_are_http_on_a_lcl_domain():
    # Issue #61: .lcl is the domain `nephos setup lcl` creates, and the platform
    # serves it over http. Guessing https from the suffix produced a redirect
    # URI that never matches what the browser sends.
    redirects, post_logout = _oidc_uris(_route_ctx())

    assert redirects == ("http://graph-demo.nephos.lcl/oauth/callback",)
    assert post_logout == ("http://graph-demo.nephos.lcl/",)
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest tests/test_zitadel_provisioning_identity.py::test_redirect_uris_are_http_on_a_lcl_domain -q
```

Expected: FAIL, actual is `https://graph-demo.nephos.lcl/oauth/callback`.

- [ ] **Step 3: Confirm nothing else calls `_route_scheme`**

```bash
grep -rn "_route_scheme" src/ tests/
```

Expected: only its definition and the one call in `_route_base_urls`. If anything else appears, stop and report — the plan assumed a single caller.

- [ ] **Step 4: Implement**

In `_route_base_urls`, replace `scheme = _route_scheme(default_domain)` with:

```python
    # ADR 20260517: Nephos-generated URLs are http. Guessing a scheme from the
    # domain suffix (issue #61) produced https redirect URIs on `.lcl`, which is
    # the domain `nephos setup lcl` creates and serves over http.
    scheme = PLATFORM_ROUTE_SCHEME
```

Delete the `_route_scheme` function entirely, and add to the imports:

```python
from nephos_api.routing import PLATFORM_ROUTE_SCHEME
```

- [ ] **Step 5: Update the now-stale warning in `routing.py`**

The comment at `routing.py:18-23` warns about `zitadel._route_scheme`, which no longer exists. Replace that block with:

```python
# ! Do not reintroduce scheme guessing here or anywhere else. `zitadel` used to
# ! infer https from any suffix that was not `.local`/`.localhost`, so
# ! `nephos.lcl` — the domain `nephos setup lcl` creates — yielded https
# ! redirect URIs for an http-served route (issue #61). Both the App
# ! redirect-URI path and the Service provisioning identity now read the
# ! constants below.
```

- [ ] **Step 6: Run to verify it passes**

```bash
uv run pytest tests/test_zitadel_provisioning_identity.py -q && uv run pytest -q
```

Expected: 6 passed in the new file; full suite green. An existing test asserting an https redirect URI is now wrong and should be updated to http — that is the fix, not a regression.

- [ ] **Step 7: Lint and commit**

```bash
uv run ruff check . && uv run ruff format --check .
```

```bash
git add -A && git commit -m "fix(zitadel): derive App redirect URIs from the platform route scheme (#61)"
```

---

## Task 5: Record the portals gap in its ADR

**Files:**
- Modify: `docs/adr/20260726-service-portals.md`

- [ ] **Step 1: Append a dated addendum**

At the end of the file, matching the repo's existing addendum style:

```markdown
## Addendum 2026-08-01: the provisioning path was left behind

This ADR moved a Service's external identity to `spec.portals` and the deploy
path followed: `providers/deployer._portal_mapping_value` derives the host from
the portal and feeds it to the provider. `core-registry` dropped the
`external-host`, `external-port`, and `external-secure` config options
accordingly.

The **binding-provisioning** path was not migrated. `provisioners/zitadel`
kept reading `external-host` from Service config, so once the option was gone
every OIDC binding blocked with `binding_provisioner_unavailable`. Nothing
caught it because no test covered a Service whose manifest had moved on, and
the deploy path — which had migrated — kept working.

Closed by deriving the same identity for provisioning:
`routing.service_portal_identity` returns the Service's first portal host with
the platform route port and scheme, `BindingProvisioningContext` carries it,
and the Zitadel provisioner reads it in preference to config. The config
fallback remains for a non-core Service that still declares those options.

The lesson worth keeping: when a value moves from one source to another, the
consumers are not always in the same subsystem as the producer. Grep for the
old key across every layer, not just the one being edited.
```

- [ ] **Step 2: Commit**

```bash
git add docs/adr/20260726-service-portals.md
git commit -m "docs(adr): record that portals left the provisioning path behind"
```

---

## Task 6: Teardown tolerates a failing provisioner

**Files:**
- Modify: `src/nephos_api/reconciler.py`
- Modify: `src/nephos_api/provisioners/registry.py`
- Test: `tests/test_engine_routing_provisioner.py` (extend), `tests/test_reconciler_runtime.py` (extend)

**Interfaces:**
- Consumes: nothing new.
- Produces: no signature changes. `EngineRoutingBindingProvisioner.deprovision_binding` becomes total — it never raises on an unroutable binding.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_engine_routing_provisioner.py`:

```python
def test_deprovision_is_a_noop_when_the_engine_is_unregistered():
    # Teardown must not strand a consumer. There is nothing to tear down
    # through an engine that does not exist.
    EngineRoutingBindingProvisioner({}).deprovision_binding(_ctx(engine="opencypher"))


def test_deprovision_is_a_noop_when_no_engine_is_declared():
    EngineRoutingBindingProvisioner({"sql": _Recorder()}).deprovision_binding(_ctx())


def test_provision_still_blocks_on_an_unregistered_engine():
    # Only teardown is best-effort. Provisioning must still fail loudly.
    with pytest.raises(RuntimeBlockedError):
        EngineRoutingBindingProvisioner({}).provision_binding(_ctx(engine="nope"))
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/test_engine_routing_provisioner.py -q
```

Expected: the two deprovision tests fail with `RuntimeBlockedError`.

- [ ] **Step 3: Make the router's teardown total**

In `src/nephos_api/provisioners/registry.py`, replace `deprovision_binding`:

```python
    def deprovision_binding(self, context: BindingProvisioningContext) -> None:
        # Teardown is best-effort in both directions: entitlements are not
        # checked, and an engine that cannot be resolved is skipped rather than
        # raised on. Refusing to tear down what we cannot route only strands the
        # consumer — an App whose binding names an unregistered engine was
        # undeletable, and the only clean exit was pointing its Service at a
        # *wrong* engine that would ignore the binding.
        try:
            engine = self._resolve_engine(context)
        except RuntimeBlockedError:
            return
        engine.deprovision_binding(context)
```

- [ ] **Step 4: Guard the App teardown caller**

In `src/nephos_api/reconciler.py` `_deprovision_app_bindings`, wrap the call. `suppress` is already imported for the sibling method:

```python
            # Same reasoning as _cleanup_service_dependent_bindings below: if
            # provider cleanup cannot run, App-side teardown must still proceed.
            # Without this an App whose provisioner raises is undeletable, and
            # `force: true` does not help — it only gates the Service dependents
            # check.
            with suppress(Exception):
                deprovision(
                    BindingProvisioningContext(
                        ...
                    )
                )
```

Keep the existing `BindingProvisioningContext(...)` body exactly as it is, including the `service_portal` argument added in Task 2 — only the wrapping changes.

- [ ] **Step 5: Pin the caller behaviour**

Append to `tests/test_reconciler_runtime.py`, following that file's existing fixture style for building a reconciler with a fake provisioner:

```python
def test_app_destroy_completes_when_the_provisioner_raises(tmp_path):
    # An App whose binding provisioner fails on teardown must still be
    # removable. Before this, the destroy reconcile threw and the App was
    # stranded with deleteRequestedAt set and nothing retrying.
    class _Raising:
        def provision_binding(self, context):
            return {"uri": "x"}

        def deprovision_binding(self, context):
            raise RuntimeError("zitadel unreachable")

    ...
```

Complete this against the file's existing helpers — locate the nearest existing destroy test and mirror its arrangement. The assertion is that the App row is gone and no exception escaped.

- [ ] **Step 6: Run and commit**

```bash
uv run pytest -q && uv run ruff check . && uv run ruff format --check .
```

```bash
git add -A && git commit -m "fix(teardown): never strand a consumer on a failing or unroutable provisioner"
```

---

## Task 7: Capped retry for blocked reconciliation requests

**Files:**
- Create: `src/nephos_api/migrations/0005_add_reconciliation_attempts.sql`
- Modify: `src/nephos_api/db.py`
- Modify: `src/nephos_api/repository.py`
- Test: `tests/test_reconciliation_retry.py` (create)

**Interfaces:**
- Consumes: `utc_now()`.
- Produces: `db.utc_now_minus(seconds: int) -> str`; `repository.RECONCILE_RETRY_ATTEMPT_CAP = 3`; `repository.RECONCILE_RETRY_INTERVAL_SECONDS = 60`; `update_reconciliation_request_state(..., increment_attempts: bool = False)`.

- [ ] **Step 1: Write the migration**

`src/nephos_api/migrations/0005_add_reconciliation_attempts.sql`:

```sql
-- ADR 20260518 called for simple capped retry and deferred it. Without an
-- attempt count a blocked request was terminal: it held a stale status while
-- nothing re-ran it, so fixing the underlying cause changed nothing.
ALTER TABLE reconciliation_requests ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0;
```

- [ ] **Step 2: Add the timestamp helper**

In `src/nephos_api/db.py`, beside `utc_now`:

```python
def utc_now_minus(seconds: int) -> str:
    """`utc_now()` shifted back, in the identical format.

    Retry cutoffs are computed here rather than as a SQL datetime expression so
    the timestamp format has exactly one definition.
    """
    return (
        (datetime.now(UTC) - timedelta(seconds=seconds))
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
```

Add `timedelta` to the existing `datetime` import.

- [ ] **Step 3: Write the failing tests**

`tests/test_reconciliation_retry.py`:

```python
from nephos_api.db import migrate_database, utc_now_minus
from nephos_api.repository import (
    RECONCILE_RETRY_ATTEMPT_CAP,
    DesiredStateRepository,
)


def _repo(tmp_path):
    db_path = tmp_path / "nephos.db"
    migrate_database(db_path=db_path)
    return DesiredStateRepository(db_path)


def _blocked_request(repo, *, attempts, updated_at):
    """Insert a blocked request directly; the public API cannot backdate one."""
    with repo.transaction() as tx:
        request = tx.create_reconciliation_request(
            target_type="app_instance",
            target_id="appinst_1",
            target_generation=1,
            action="destroy",
            target_snapshot={"slug": "graph-demo"},
        )
    with repo.transaction() as tx:
        tx._connection.execute(
            "UPDATE reconciliation_requests "
            "SET state='blocked', attempts=?, updated_at=? WHERE id=?",
            (attempts, updated_at, request["id"]),
        )
    return request


def test_blocked_request_is_reclaimed_after_the_retry_interval(tmp_path):
    repo = _repo(tmp_path)
    _blocked_request(repo, attempts=1, updated_at=utc_now_minus(600))

    claimed = repo.claim_next_reconciliation_request()

    assert claimed is not None
    assert claimed["state"] == "running"


def test_blocked_request_is_not_reclaimed_before_the_retry_interval(tmp_path):
    repo = _repo(tmp_path)
    _blocked_request(repo, attempts=1, updated_at=utc_now_minus(5))

    assert repo.claim_next_reconciliation_request() is None


def test_blocked_request_stops_being_reclaimed_at_the_cap(tmp_path):
    repo = _repo(tmp_path)
    _blocked_request(
        repo, attempts=RECONCILE_RETRY_ATTEMPT_CAP, updated_at=utc_now_minus(600)
    )

    assert repo.claim_next_reconciliation_request() is None


def test_pending_work_is_claimed_ahead_of_a_retry_eligible_blocked_request(tmp_path):
    # A permanently blocked request must not starve new work on the single
    # serialized worker while it burns its attempts.
    repo = _repo(tmp_path)
    _blocked_request(repo, attempts=1, updated_at=utc_now_minus(600))
    with repo.transaction() as tx:
        pending = tx.create_reconciliation_request(
            target_type="app_instance",
            target_id="appinst_2",
            target_generation=1,
            action="install",
            target_snapshot={"slug": "other"},
        )

    claimed = repo.claim_next_reconciliation_request()

    assert claimed["id"] == pending["id"]


def test_marking_blocked_increments_attempts(tmp_path):
    repo = _repo(tmp_path)
    with repo.transaction() as tx:
        request = tx.create_reconciliation_request(
            target_type="app_instance",
            target_id="appinst_3",
            target_generation=1,
            action="install",
            target_snapshot={"slug": "third"},
        )

    with repo.transaction() as tx:
        tx.update_reconciliation_request_state(
            request_id=request["id"],
            state="blocked",
            error="nope",
            increment_attempts=True,
        )

    row = repo.get_reconciliation_request(request["id"])
    assert row["attempts"] == 1
```

If `get_reconciliation_request` does not exist, read the row with a direct query in the test rather than adding a repository method for test convenience.

- [ ] **Step 4: Run to verify they fail**

```bash
uv run pytest tests/test_reconciliation_retry.py -q
```

Expected: `ImportError` on `RECONCILE_RETRY_ATTEMPT_CAP`.

- [ ] **Step 5: Implement the repository changes**

Add module-level constants near the top of `src/nephos_api/repository.py`:

```python
# ADR 20260518: "Simple capped retry is the intended model." Fixed interval
# rather than exponential backoff — one serialized worker on a local-first
# install has no contention for backoff to relieve, and the cap already bounds
# a permanently blocked request to about three minutes.
RECONCILE_RETRY_ATTEMPT_CAP = 3
RECONCILE_RETRY_INTERVAL_SECONDS = 60
```

Replace the SELECT in `claim_next_reconciliation_request`:

```python
            row = connection.execute(
                """
                SELECT *
                FROM reconciliation_requests
                WHERE state = 'pending'
                   OR (
                        state = 'blocked'
                        AND attempts < ?
                        AND updated_at <= ?
                   )
                ORDER BY (state <> 'pending'), created_at
                LIMIT 1
                """,
                (
                    RECONCILE_RETRY_ATTEMPT_CAP,
                    utc_now_minus(RECONCILE_RETRY_INTERVAL_SECONDS),
                ),
            ).fetchone()
```

Add `increment_attempts` to the state update:

```python
    def update_reconciliation_request_state(
        self,
        *,
        request_id: str,
        state: str,
        error: str | None = None,
        increment_attempts: bool = False,
    ) -> None:
        now = utc_now()
        self._connection.execute(
            f"""
            UPDATE reconciliation_requests
            SET state = ?,
                error = ?,
                updated_at = ?
                {", attempts = attempts + 1" if increment_attempts else ""}
            WHERE id = ?
            """,
            (state, error, now, request_id),
        )
```

Import `utc_now_minus` alongside the existing `utc_now`.

- [ ] **Step 6: Run to verify they pass**

```bash
uv run pytest tests/test_reconciliation_retry.py -q && uv run pytest -q
```

Expected: 5 passed; full suite green.

- [ ] **Step 7: Lint and commit**

```bash
uv run ruff check . && uv run ruff format --check .
```

```bash
git add -A && git commit -m "feat(reconciler): capped retry for blocked requests (ADR 20260518)"
```

---

## Task 8: Blocked status says which attempt it is

**Files:**
- Modify: `src/nephos_api/reconciler.py`
- Modify: `docs/adr/20260518-reconciliation-execution-model.md`

**Interfaces:**
- Consumes: `RECONCILE_RETRY_ATTEMPT_CAP`, `increment_attempts` (Task 7).

- [ ] **Step 1: Increment attempts and annotate the message**

In `_mark_blocked`, pass `increment_attempts=True` and append the attempt count to the status message:

```python
    def _mark_blocked(
        self,
        request: dict[str, object],
        *,
        reason: str,
        message: str,
    ) -> None:
        # The attempt suffix is the difference between "still converging" and
        # "given up". Without it the status reads identically in both cases,
        # and an operator who fixed the real cause and waited would wait
        # forever.
        attempts = int(request.get("attempts") or 0) + 1
        if attempts >= RECONCILE_RETRY_ATTEMPT_CAP:
            annotated = f"{message} (attempt {attempts}, no further retries)"
        else:
            annotated = (
                f"{message} (attempt {attempts} of {RECONCILE_RETRY_ATTEMPT_CAP})"
            )
        with self._repository.transaction() as tx:
            tx.update_reconciliation_request_state(
                request_id=str(request["id"]),
                state="blocked",
                error=annotated,
                increment_attempts=True,
            )
```

Keep the rest of the method as it is, but pass `annotated` as the snapshot `message` and in the evidence entry.

Import `RECONCILE_RETRY_ATTEMPT_CAP` from `nephos_api.repository`.

- [ ] **Step 2: Run the suite and fix message assertions**

```bash
uv run pytest -q
```

Existing tests asserting an exact blocked message will now fail on the suffix. Update them to match — the suffix is the intended change. Prefer `in` over `==` only where the test's subject is the reason, not the wording.

- [ ] **Step 3: Append the ADR addendum**

To `docs/adr/20260518-reconciliation-execution-model.md`:

```markdown
## Addendum 2026-08-01: capped retry is implemented

This ADR stated that simple capped retry was the intended model and allowed it
to be deferred from API 0.0.1. It was deferred and then forgotten, which made
`blocked` terminal in practice: `claim_next_reconciliation_request` selected
only `pending`, so a request that blocked once was never re-run. Observed on a
live install holding a stale status for over twenty minutes while the
underlying cause had already been fixed — nothing picked the fix up, and
re-POSTing the lifecycle action was the only way to queue another attempt.

Now implemented: `reconciliation_requests.attempts` (migration 0005), a claim
that also selects blocked requests under the cap whose `updated_at` is older
than the retry interval, and pending work ordered ahead of retry-eligible
blocked work so a permanently blocked request cannot starve the single
serialized worker.

Fixed interval of 60 seconds, capped at 3 attempts. Exponential backoff was
considered and rejected: with one serialized worker on a local-first install
there is no contention for backoff to relieve, and the cap already bounds a
permanently blocked request to roughly three minutes.

Blocked status messages carry the attempt count, so an exhausted request is
distinguishable from one still converging.
```

- [ ] **Step 4: Lint and commit**

```bash
uv run pytest -q && uv run ruff check . && uv run ruff format --check .
```

```bash
git add -A && git commit -m "feat(reconciler): report which retry attempt a blocked request is on"
```

---

## Task 9: Live validation on k3d

The unit suite was green before every one of these defects. This is the gate that matters.

**Files:** none. This task produces observations.

- [ ] **Step 1: Build and deploy the fixed API**

```bash
docker build -t nephos-api:dev .
```

```bash
k3d image import nephos-api:dev --cluster nephos
```

```bash
kubectl -n nephos-system rollout restart deploy/nephos-api && kubectl -n nephos-system rollout status deploy/nephos-api --timeout=180s
```

The pod's registry clone must be clean for startup sync to succeed — it was left clean, but verify:

```bash
kubectl -n nephos-system exec deploy/nephos-api -- git -C /data/registries/core-registry status --porcelain
```

Expected: empty.

- [ ] **Step 2: Publish the demo chart and catalog entry**

Follow `~/projects/nephos-graph-demo/docs/plans/2026-08-01-graph-demo.md` Task 11 steps 2 and 3: package the chart, serve it from the in-cluster nginx, point `app.yaml`'s `chart.repository` at it, and `kubectl cp` `apps/graph-demo` plus the modified `services/arcadedb/service.yaml` into the pod's registry clone.

**Cleanup obligation:** those copies leave the clone dirty, which breaks the next startup sync. Restore it with `git checkout -- . && git clean -fd` inside the pod before finishing.

- [ ] **Step 3: Install and observe**

```bash
curl -sS -X POST http://127.0.0.1:8099/apps -H 'content-type: application/json' -d '{"catalogRef": {"kind": "App", "name": "graph-demo"}, "instanceName": "graph-demo"}'
```

Expected within a few minutes:

| Resource | Expected |
|---|---|
| App `graph-demo` | `runtime_deployed` |
| Binding `auth` | `binding_secret_ready` |
| Binding `graph` | blocked, `provisioning_engine_unknown` — unchanged and correct |

If `auth` still blocks on `external-host`, increment A did not take effect — check the image actually rebuilt and the rollout completed.

- [ ] **Step 4: Verify the issuer and redirect scheme**

```bash
kubectl -n app-graph-demo get secret nephos-bind-auth -o jsonpath='{.data.issuerUrl}' | base64 -d
```

```bash
kubectl -n app-graph-demo get secret nephos-bind-auth -o jsonpath='{.data.redirectUris}' | base64 -d
```

Expected: `http://auth.nephos.lcl` and `["http://graph-demo.nephos.lcl/oauth/callback"]` — both http. An https redirect URI means Task 4 did not land.

- [ ] **Step 5: Sign in**

Open `http://graph-demo.nephos.lcl` and complete the Zitadel login. Expect to land on `/nodes` showing the blocked-graph panel naming `nephos-bind-graph` and the five missing keys.

Record what actually happens, including anything that differs.

- [ ] **Step 6: Destroy on the first attempt**

```bash
curl -sS -X POST http://127.0.0.1:8099/apps/graph-demo/actions/destroy -H 'content-type: application/json' -d '{"confirm": "destroy graph-demo"}'
```

Expected: the App reaches 404 with **no** second destroy POST and **no** temporary manifest edits. This is the proof for increment B.

- [ ] **Step 7: Clean up**

Revert `app.yaml`'s chart repository, tear down the chart server deployment/service/configmap, and restore the pod's registry clone. Confirm:

```bash
kubectl -n nephos-system exec deploy/nephos-api -- git -C /data/registries/core-registry status --porcelain
```

Expected: empty.

---

## Self-Review

**Spec coverage.** Defect 1 → Tasks 1–3. Defect 5 → Task 4. Defect 2 → Task 6 step 4. Defect 3 → Task 6 step 3. Defect 4 → Tasks 7–8. Docs → Tasks 5 and 8. Validation → Task 9. The spec's "existing installs self-heal" property is exercised by Task 9 step 3 against the already-installed `auth` Service, whose binding re-provisions with the new identity.

**Placeholders.** One deliberate gap: Task 6 step 5's reconciler test is sketched rather than written out, because it must be built on `tests/test_reconciler_runtime.py`'s existing fixtures, which vary by test and cannot be reproduced faithfully without reading the neighbouring test. The instruction says which existing test to mirror and what to assert. Everything else carries complete content.

**Type consistency.** `ServicePortalIdentity(host, port, secure)` is defined in Task 1, carried in Task 2, and read in Task 3 by attribute — consistent throughout. `service_portal_identity` keeps the same keyword signature at both call sites. `RECONCILE_RETRY_ATTEMPT_CAP` and `increment_attempts` are introduced in Task 7 and consumed in Task 8 under those exact names. `utc_now_minus` is defined in Task 7 step 2 and used in step 5 and in the Task 7 tests.
