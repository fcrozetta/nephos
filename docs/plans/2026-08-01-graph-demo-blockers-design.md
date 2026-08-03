# Fixing the graph-demo blockers: design

Status: approved 2026-08-01.

## Context

Building a third-party App against Nephos (`graph-demo`: OIDC sign-in plus
ArcadeDB over Cypher) surfaced five platform defects. The App itself was
built, containerized, charted, validated against the catalog loader, and
accepted by the API — and then could neither install nor be deleted, for
reasons that had nothing to do with it.

The findings are written up in full in that project's
`docs/nephos-app-authoring-report.md`, with every citation independently
fact-checked against this repository. This document is the fix.

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

Scope decided 2026-08-01: **the five defects only.** Building an `opencypher`
provisioning engine — which is what would make the demo's graph half actually
work — is a feature, not a fix, and is out of scope here. Its output contract
is already settled by ADR 20260630 if and when it is built.

## The defects

| # | Defect | Family |
|---|---|---|
| 1 | OIDC binding provisioning reads `external-host` from Service config, which the portals ADR deleted | A |
| 5 | `_route_scheme` infers `https` for `nephos.lcl`, contradicting the HTTP-only ADR (issue #61) | A |
| 2 | App teardown calls `deprovision()` unguarded, so a failing provisioner strands the App | B |
| 3 | Engine resolution raises during teardown, so an unregistered engine also strands the App | B |
| 4 | A blocked reconciliation request is never retried | B |

Two independent families. A unblocks install and login; B unblocks removal and
recovery. Each ships on its own.

---

## A — Portal-derived provisioning identity

### The problem

`provisioners/zitadel.py` resolves the host it provisions against from Service
**config**:

```python
def _provisioning_domain(context):
    return str(_config_value(context, "external-host", "externalHost"))
```

ADR 20260726 moved a Service's external identity to `spec.portals`, and
`core-registry` commit `fcfac27` deleted `external-host`, `external-port`, and
`external-secure` from the Zitadel manifest accordingly. The **deploy** path was
migrated — `providers/deployer.py` `_portal_mapping_value` derives the host from
the portal. The **binding-provisioning** path was not.
`BindingProvisioningContext` carries `app_routes` and `platform_domains` but
nothing portal-derived, so the provisioner structurally cannot see the host the
portal resolved.

Every OIDC binding for every App blocks with `binding_provisioner_unavailable`.

### The fix

Give the provisioning path the same derivation the deploy path already uses.

**`provisioners/base.py`** gains a small frozen dataclass and one optional
context field:

```python
@dataclass(frozen=True)
class ServicePortalIdentity:
    """A Service's canonical external address, derived from its first portal."""
    host: str
    port: int
    secure: bool
```

`BindingProvisioningContext` gains `service_portal: ServicePortalIdentity | None
= None`. Optional so every existing construction site and test factory keeps
working unchanged.

**Which portal.** The Service's **first** portal, matching
`routing.service_portal_host_prefix`, which gives the first portal the bare
`<service-slug>.<domain>` host. That bare host is the Service's canonical
address — it is why installing Zitadel under the slug `auth` yields the issuer
`auth.nephos.lcl`. Zitadel declares exactly one portal (`console`). A Service
whose first portal is not its identity is not expressible today; the rule is
documented where it is derived so a future case is a deliberate change rather
than a silent mismatch.

**Derivation**, reusing what already exists:

```
portal_canonical_domain(repository.list_platform_domains())
  -> service_portal_host(service_slug, portal_name, domain, is_first_portal=True)
  -> PLATFORM_ROUTE_PORT / PLATFORM_ROUTE_SECURE
```

`None` when the Service declares no portals, or when no platform domain is
portal-eligible. Both are legitimate states, not errors, and the consumer
decides what to do about them.

**Populated at all four construction sites**: `reconciler.py` (app-binding
provisioning, app-binding deprovisioning, service-dependent cleanup) and
`providers/deployer.py` (service-to-service dependencies).

**`provisioners/zitadel.py`** reads the portal identity first and falls back to
config:

- `_provisioning_domain` → `context.service_portal.host`, else `external-host`
  config, else block.
- `_provisioning_port` → `context.service_portal.port`, else `external-port`
  config, else the existing default.
- `_provisioning_secure` → `context.service_portal.secure`, else
  `external-secure` config, else the existing default.

Portal-first is the correction. The config fallback is kept deliberately: a
non-core registry Service may still declare those options, and three lines of
fallback is cheaper than breaking it. Blocking happens only when neither source
exists, and the message names both.

### Defect 5 (issue #61) falls out of the same change

`_issuer_url` is built from `_provisioning_domain`/`_port`/`_secure`, so once
those come from the portal, the issuer stops guessing.

The remaining call site is App redirect URIs: `_route_base_urls` uses
`_route_scheme(default_domain)`, which returns `https` for any suffix that is
not `.local`/`.localhost` — including `nephos.lcl`, the domain `nephos setup
lcl` creates. Replace it with `routing.PLATFORM_ROUTE_SCHEME` and delete
`_route_scheme`.

`routing.py:18-23` carries a warning comment about that exact function. Once the
function is gone the comment is stale and must be updated in the same change,
or the next reader is warned about something that no longer exists.

### Existing installs

They self-heal, and this was verified rather than assumed:
`_redacted_binding_output_summary` stores no `values` key, so
`_binding_output_values` always returns `None` and **every binding reconcile
calls `provision_binding` again**. Zitadel's Pulumi stack is keyed by binding
id, so a changed `redirect_uris` updates the existing application in place
rather than orphaning it. A test pins this: a second `provision_binding` on a
binding whose route scheme changed must reach the provisioner, not short-circuit.

---

## B — Teardown and retry robustness

### Defect 2: App teardown is unguarded

`reconciler.py` `_deprovision_app_bindings` calls `deprovision(context)` with no
`try`/`except`. Fifty lines below, `_cleanup_service_dependent_bindings` wraps
the identical call in `with suppress(Exception)`, carrying a comment explaining
exactly why teardown must not block on provider cleanup.

The reasoning is right and was applied to only one of the two paths. Apply the
same guard, with the same reasoning stated locally.

### Defect 3: engine resolution raises during teardown

`provisioners/registry.py` `EngineRoutingBindingProvisioner.deprovision_binding`
resolves the engine before doing any teardown work, and `_resolve_engine` raises
on both an unregistered engine and an absent one. Its own inline comment says
teardown stays best-effort — but that only covers the entitlements check above
it.

Make the teardown path tolerate an unresolvable engine and return. There is
nothing to tear down through an engine that does not exist, and refusing to
proceed only strands the consumer.

Defect 2's guard alone would mask this. Both are fixed: the caller should not
depend on the router behaving, and the router should not raise on a teardown it
cannot route. Fixing only the caller leaves the same trap for the next call site.

### Defect 4: blocked requests are never retried

`repository.claim_next_reconciliation_request` selects `state = 'pending'` only.
A request marked `blocked` is terminal — observed holding a stale `observedAt`
for over twenty minutes while the underlying cause was fixed, with nothing
picking the fix up.

ADR 20260518 already states the intent: *"Simple capped retry is the intended
model. Automatic retry may be deferred from API 0.0.1 if it adds too much
implementation weight."* This implements it rather than deciding anything new.

**Migration `0005_add_reconciliation_attempts.sql`** adds
`attempts INTEGER NOT NULL DEFAULT 0` to `reconciliation_requests`.

**`repository.py`**:
- `claim_next_reconciliation_request` also selects rows where
  `state = 'blocked' AND attempts < :cap AND updated_at <= :cutoff`.
  Ordering is `ORDER BY (state <> 'pending'), created_at` — pending work sorts
  ahead of every retry-eligible blocked row, so a permanently-blocked request
  cannot starve new work while it burns its three attempts. The existing index
  is on `(state, created_at)`; confirm the new predicate still uses it, and add
  one if not.
- Marking a request `blocked` increments `attempts`.
- The cutoff is computed in Python and passed as a parameter, not derived in
  SQL, so the interval stays one named constant rather than a datetime
  expression embedded in a query string.

**Policy: a fixed 60-second interval, capped at 3 attempts.** ADR 20260518 says
"simple", and with one serialized worker on a local-first install, exponential
backoff is machinery with no payer. The cap bounds a permanently-blocked request
to roughly three minutes of retrying.

**Observability.** The blocked status message gains an attempt suffix, so an
exhausted request is distinguishable from one still waiting. This is the half of
defect 4 that actually caused harm: the status read like a live state while
nothing was happening, and an operator who fixed the real cause and waited would
have waited forever.

---

## Testing

Unit tests per change, matching the repository's existing style — plain
`test_<behaviour>` names, module-level `_helper` factories, direct asserts, no
docstrings. `tests/test_engine_routing_provisioner.py` already has a `_ctx(...)`
factory with defaults, so the new optional context field does not disturb it.

Behaviours worth pinning, chosen because each fails silently otherwise:

- Portal identity is derived from the **first** portal, and is `None` when the
  Service has no portals or no domain is portal-eligible.
- Zitadel provisioning prefers the portal over config, falls back to config when
  there is no portal, and blocks naming both when there is neither.
- The issuer URL and App redirect URIs are `http` on a `.lcl` domain — the
  regression that issue #61 describes.
- A second `provision_binding` on an already-provisioned binding reaches the
  provisioner (the self-heal property above).
- App teardown completes when the provisioner raises.
- Teardown completes when the engine is unregistered, and when none is declared.
- A blocked request is re-claimed after the interval, is not re-claimed before
  it, and stops being re-claimed at the cap.
- Pending work is claimed ahead of retry-eligible blocked work.

## Documentation

Dated addenda, matching the repository's existing ADR practice:

- `20260726-service-portals.md` — the provisioning path is now portal-derived.
  That ADR migrated the deploy path and left this one behind; the addendum
  records the gap and its closure.
- `20260518-reconciliation-execution-model.md` — capped retry is implemented,
  with the chosen interval and cap, and is no longer deferred.

## Delivery

Two PRs off updated `main`, A then B, stacked. They touch different subsystems
and each is independently useful: A makes an App with an OIDC binding
installable; B makes any App with a failing binding removable.

## Validation

Unit tests are necessary but not sufficient — every one of these defects passed
a green suite before. The real gate is a live reinstall of `graph-demo` on the
k3d cluster:

1. App `graph-demo` reaches `runtime_deployed`.
2. Binding `auth` reaches `binding_secret_ready`.
3. Binding `graph` still blocks with `provisioning_engine_unknown` — unchanged
   and correct; no `opencypher` engine is in scope.
4. Sign-in through Zitadel completes and lands on `/nodes`.
5. The notes page renders the honest blocked-graph panel.
6. `destroy` completes on the **first** attempt, with no manual re-POST and no
   temporary manifest edits.

Step 6 is the one that proves B. Steps 1, 2, and 4 prove A.
