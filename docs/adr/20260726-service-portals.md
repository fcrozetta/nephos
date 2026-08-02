# Service portals as declared platform ingress intent

- Status: accepted
- Date: 2026-07-26
- Tags: ingress, services, catalog, manifest-schema, security, visibility

Technical Story: resolves the open questions "Service-surface route shape for
Zitadel login/admin UI" and "whether generic Service surfaces need a shared
response shape before the first implementation"
(`.agents/context/nephos-open-questions.md`). Amends the Phase 1 "Service Admin
Routes" clause of ADR 20260517 (ingress and visibility model).

## Context and Problem Statement

A Service may own a browser surface: Zitadel has a login/console UI, ArcadeDB
has Studio. Today the platform has no way to express that.

`AppSpec` carries `routes: list[AppRoute]`; `ServiceSpec` carries no equivalent.
The whole ingress path is app-only end to end:

- `Reconciler._app_routes` reads `manifest.spec.routes` from App rows only.
- `KubernetesRuntime.ensure_app_ingresses` asserts an `app_instance` namespace.
- `_route_snapshots` — the only producer of `canonicalUrl` / `aliases` — is
  reachable only from the App read payload.

ADR 20260517 states this deliberately:

> Services do not expose admin routes through Nephos ingress in Phase 1.
>
> Service management stays through Nephos API/CLI operations and future typed
> Service operations.

Two consequences followed.

**Zitadel reinvented ingress inside its provider.** The Service manifest carries
`ingress-enabled`, `ingress-class-name`, and `external-host` config options that
map to Helm values consumed by a provider-private `_service_ingress` helper. The
hostname is an operator-entered string whose default is assembled in the
manifest:

```python
{"name": "external-host", "type": "string", "default": f"zitadel.{internal_domain}"}
```

That host is invented by the catalog entry, not derived from the
`platform_domains` rows that are the runtime source of truth for routing. It is
the same divergence class the 2026-07-18 amendment to the ingress-root-domain
ADR already had to correct once ("one source, no silent divergence between
configuration and behavior"). Because the platform never learns the URL exists,
it appears in no status payload and no API response.

**ArcadeDB has no hatch at all.** Its provider publishes a Service port named
`http` on 2480 — that is Studio — and nothing routes to it. The UI is
unreachable by design.

The direction was already selected. `nephos-open-questions.md` records as
accepted direction: "Zitadel login/admin UI are Service surfaces/routes, not a
separate App", with the *shape* left open. This ADR fixes the shape.

How should a Service declare a browser surface, and what generates its URL?

## Decision Drivers

- **Declared, not ad-hoc.** Portal reachability is platform intent belonging in
  the Service description, not per-provider chart plumbing that each registry
  author re-derives.
- **Default-deny exposure.** Root domains include user-tunnelled public suffixes
  (`nephos.fcrozetta.app`). Declaring an admin console must never be sufficient
  to publish it on the internet.
- **One source of truth for the host.** The platform generates the hostname;
  the Service consumes it. A Service must not invent the host it is reachable at.
- **Symmetry where it is free, asymmetry where it is honest.** Reuse App route
  machinery and naming conventions; do not copy fields that would carry no
  meaning for portals.
- **Discoverable or it does not exist.** A portal absent from status and the API
  is not a product feature.

## Considered Options

Host pattern:

- App-symmetric, first portal bare `<service-slug>.<domain>`
- always portal-prefixed `<portal>.<service-slug>.<domain>`
- flat capability-style portal name `<portal>.<domain>`
- reserved infrastructure label `<service-slug>.svc.<domain>`

Exposure control:

- default-deny, opt-in per root domain
- default-deny to the default root domain only
- per-portal `visibility` field in the manifest
- identical to App routes (every configured root domain)

Zitadel `external-host`:

- derive from the resolved portal host
- keep as manual config, validate against the portal host
- keep as manual config, unvalidated
- leave Zitadel on its provider-private ingress

## Decision Outcome

Chosen: **`portals` on `ServiceSpec`, generating platform-owned Ingress on
explicitly portal-eligible root domains only, with the resolved host fed back to
providers through a new runtime mapping source.**

### 1. `ServiceSpec.portals`

```yaml
spec:
  portals:
    - name: studio
      displayName: ArcadeDB Studio
      target:
        port: http
```

```python
class ServicePortal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    displayName: str | None = None
    target: RouteTarget
```

`ServiceSpec` gains `portals: list[ServicePortal] = Field(default_factory=list)`.
`RouteTarget` is reused unchanged — it already rejects YAML booleans parsing as
`int`. `name` is validated as a machine identifier and, like App route names,
against the generated Kubernetes object name length.

`displayName` exists because the purpose of this feature is discoverability; a
portal list rendering `studio` rather than `ArcadeDB Studio` is a worse product
for zero schema saving.

**No `visibility` field.** Exposure is a property of the root domain (§3), not of
the manifest. `AppRoute.visibility` is a required `Literal["local"]`; mirroring
it here would add a field that is either meaningless or a second, conflicting
exposure control that a community registry author could set. Adding an optional
`visibility` later remains backward compatible under `extra="forbid"`.

### 2. Host pattern: App-symmetric, first portal bare

```text
<service-slug>.<root-domain>              # first portal
<portal>.<service-slug>.<root-domain>     # subsequent portals
```

```text
auth.nephos.lcl                # zitadel installed as instance `auth`
arcadedb.nephos.lcl            # arcadedb's studio portal
metrics.arcadedb.nephos.lcl    # a second arcadedb portal
```

Identical to App routes, where route index 0 is bare and later routes are
prefixed.

**Why the portal name drops out of the first host.** A portal host is a durable,
user-visible identity — for Zitadel it *is* the OIDC issuer, baked into every
registered client's redirect URIs. It should therefore name a *role*, not an
implementation. Making the first host bare moves that naming to the instance
slug, which the operator chooses at install (`instanceName` on the install
request): installing Zitadel as `auth` yields `auth.nephos.lcl`, and a later
migration to Logto installs Logto as `auth` and keeps the issuer.

The rejected alternative was to let a portal declare a flat, capability-style
name (`auth`) directly. That cannot work: the catalog already carries two
`oidc/oidc` providers (`zitadel`, `logto`), so both would declare portal `auth`
and claim the same host, and they could never be installed side by side — which
is precisely what capability abstraction exists to allow. The registry author
cannot pick a globally unique role name because they do not know what else is
installed; the operator can, and already does when choosing a slug.

Runtime objects reuse existing conventions:

- Ingress `nephos-route-<portal>` in namespace `svc-<service-slug>`
- `target.port` stays the semantic port name or number
- the backend Service is resolved at reconcile time, not derived (see below)

**Consequence: Service portal hosts now share the App hostname namespace.** An
App and a portal-bearing Service can both claim `<slug>.<domain>`. ADR 20260517
already requires failing loudly on collisions rather than suffixing, so install
now rejects a resource whose generated host prefixes intersect an installed one
(`409 hostname_conflict`). Prefixes are compared rather than full hosts: every
root domain receives the same prefixes, so a collision on one is a collision on
all. Because a slug cannot contain a dot, a one-label prefix can never equal a
two-label prefix, which bounds the collision surface to equal slugs.

An earlier revision of this ADR chose *always* portal-prefixed
(`console.zitadel.nephos.lcl`) to make collisions unreachable by construction.
That bought collision-freedom at the cost of baking the implementation name into
the OIDC issuer, and was reversed once the issuer implication was concrete.

Runtime objects:

- Ingress `nephos-route-<portal>` in namespace `svc-<service-slug>`
- `target.port` stays the semantic port name or number
- the backend Service is **resolved at reconcile time**, not derived (see below)

#### The backend Service cannot be derived

An earlier draft of this ADR asserted the backend is
`runtime_name("service_instance", slug)` — i.e. `svc-<slug>` — by analogy with the
App path, where ADR 20260517 requires the chart to expose a Service matching the
release name. **That is wrong for Services**, and a live deploy proved it: Service
runtime providers append a component suffix, so the real names are
`svc-arcadedb-arcadedb`, `svc-postgres-postgresql`, `svc-zitadel-zitadel`. An
Ingress pointing at `svc-arcadedb` is accepted by Kubernetes, resolves to nothing,
and serves 404.

Three options were available: name the Service in the manifest (leaks Kubernetes
naming into the catalog contract, which this ADR's own `target.port` design
avoids), rename provider Services to the release name (breaks the in-cluster DNS
names existing bindings already resolve, e.g. Zitadel's `databaseHost`), or
resolve it.

Chosen: **resolve by the labels providers already set.** Portal ingress selects
Services in the Service namespace matching
`app.kubernetes.io/managed-by=nephos` and `nephos.pro/runtime-name=svc-<slug>`,
narrowed to the one exposing the portal's `target.port`. Zero matches or more than
one both block loudly; neither picks arbitrarily, and no Kubernetes Service name
enters the manifest.

This makes `nephos.pro/runtime-name` part of the Service runtime provider contract
rather than an incidental label.

Because the Ingress lives in the Service namespace, `nephos-route-<portal>`
cannot collide with an App's Ingress of the same route name.

**Zitadel's host is the instance slug.** Installed as `zitadel` it is
`zitadel.<domain>` (unchanged from before this ADR); installed as `auth` it is
`auth.<domain>`. Either way the choice is the operator's and is fixed at install:
the OIDC issuer identity and every registered client redirect URI bind to it, so
changing the slug later is a breaking change, not a rename.

Note that Zitadel additionally self-generates a non-primary vanity instance
domain (`<instance-name>-<random>.<ExternalDomain>`) on first-instance bootstrap.
Nephos neither sets nor routes it; the primary domain and issuer are the portal
host. It is noise in Zitadel's own domain list, not a Nephos concern.

### 3. Exposure: default-deny, opt-in per root domain

`platform_domains` gains a column:

```sql
-- 0003_add_platform_domain_service_portals.sql
ALTER TABLE platform_domains
ADD COLUMN allows_service_portals INTEGER NOT NULL DEFAULT 0
CHECK (allows_service_portals IN (0, 1));
```

`PlatformDomain` gains `allows_service_portals: bool`. Portal Ingress rules are
generated **only** for root domains with the flag set. App routes are unchanged
and still fan out to every configured root domain.

Semantic configuration shape:

```yaml
rootDomains:
  - name: local
    domain: nephos.lcl
    default: true
    allowsServicePortals: true
  - name: cloudflare
    domain: nephos.fcrozetta.app
```

`GET /platform/config/domains` exposes `allowsServicePortals`, and the flag needs
add-time support plus a toggle action consistent with the existing mutation
envelope.

Rationale: `_app_ingress` emits one host rule per configured domain. Inheriting
that unchanged means declaring a portal on ArcadeDB publishes Studio at
`arcadedb.nephos.fcrozetta.app` the moment that root domain exists — an admin
database console on a public tunnel, behind only a root password. Default-deny
inverts that: exposure becomes an explicit operator act on a specific domain,
recorded in platform desired state and auditable there.

**A fresh install has zero portal-eligible domains**, so a declared portal
reconciles to no Ingress. That must be reported, not silent: status reports the
portal as unpublished with a reason, in the spirit of the ADR 20260517 rule that
a non-serving route must not be presented as healthy.

### 4. `external-host` derived from the portal

`MappingSource.kind` gains `"portal"`:

```yaml
- from:
    kind: portal
    name: console
    field: host
  to:
    helmValue: externalHost
```

Resolved fields: `host`, `port`, `scheme`, `secure`, `url`. Resolution is a third
branch in `ProviderDeployer._runtime_mapping_value`, alongside `config` and
`binding`. An unresolvable portal name or unknown field blocks loudly with
`runtime_mapping_source_missing`, matching the binding path — it does not fall
back to a guessed value.

Zitadel then:

- drops `ingress-enabled` and `ingress-class-name` (the platform owns the
  Ingress; the provider stops calling `_service_ingress`)
- derives `external-host`, `external-port`, and `external-secure` from its
  `console` portal instead of accepting them as operator config

This removes an entire misconfiguration class: a Zitadel whose issuer identity
disagrees with the hostname the ingress actually serves.

### 5. Status and API shape

Service read payloads gain a `portals` array mirroring App `routes` — `name`,
`displayName`, `target`, `canonicalUrl`, `aliases`, `status` — plus `published`
and `unpublishedReason`, which App routes do not need because App routes bind to
every configured domain and so are never unpublishable.

`canonicalUrl` is built from the default root domain when that domain is
portal-eligible, and otherwise from the first eligible domain by name. The
fallback is the common case rather than an edge case: the default domain is
typically the public/tunnelled one while only the local domain is portal-eligible,
and treating that as "no URL" would report a reachable portal as unreachable. When
no domain is eligible, `canonicalUrl` is `null`, `published` is `false`, and
`unpublishedReason` is `no_portal_eligible_domain`.

This answers the second open question: Service surfaces share the App route
response shape rather than inventing a parallel one.

### Blocking is split between the two consumers

The Ingress path and the runtime-mapping path deliberately disagree on what an
ineligible domain means:

- **Ingress reconcile tolerates it.** No eligible domain deletes any previously
  generated portal Ingress and succeeds. The Service is healthy; only its UI is
  unreachable, so blocking install would punish the default-deny default. It also
  makes revoking a domain's eligibility actually unpublish the surface rather than
  leaving it exposed.
- **A `kind: portal` mapping blocks it** with `portal_domain_not_eligible`. A
  provider consuming a portal host is binding its own external identity to it, so
  deploying with a placeholder would yield a running Service that silently fails
  authentication.

Consequence: a Service that only declares a portal installs fine with no eligible
domain; a Service that also maps the portal into its runtime (Zitadel) requires
one. That is visible in `nephos-console` as a blocked reason, not a silent
misconfiguration.

### Blocking dependency: route scheme

`canonicalUrl` for portals cannot be correct until issue #61 is resolved. Two
implementations already disagree:

- `_route_snapshots` hardcodes `http://`
- `zitadel._route_scheme` guesses from `.localhost` / `.local` suffixes

For App routes a wrong scheme is a cosmetic status defect. For a Zitadel portal
feeding `external-secure`, it decides OIDC issuer correctness — a suffix guess
becomes load-bearing for authentication. Extending the suffix guess to portals is
therefore not acceptable.

Resolution taken: the portal path uses a single constant in `nephos_api.routing`
that conforms to the accepted ADR 20260517 position (Phase 1 Nephos-managed
ingress is HTTP-only; generated URLs use `http://`). That is compliance with an
existing accepted decision, not a new one, and it removes any inference from the
portal path.

`zitadel._route_scheme` is deliberately left alone: it builds **App** OIDC
redirect URIs, and changing that alters client registration on the one working
end-to-end path. #61 remains open for exactly that call site, and `routing.py`
carries a pointer to it so the divergence is discoverable rather than forgotten.

### Rollout ordering

`ServiceSpec` is `extra="forbid"`, so a `portals:` key in a registry manifest
breaks catalog loading for any nephos-api that predates this schema. Ordering is
forced:

1. nephos-api: schema, migration, reconciler, runtime, mapping source, API shape
2. core-registry: `portals` on `arcadedb` and `zitadel`, Zitadel config options
   removed in the same change

### Positive Consequences

- ArcadeDB Studio and the Zitadel console become reachable through the platform,
  with URLs visible in status and the API.
- One ingress mechanism for Services instead of per-provider chart plumbing;
  future Services declare a portal instead of re-deriving hosts.
- Admin surfaces are default-unexposed; publishing one is explicit and auditable
  in platform desired state.
- Zitadel's external host stops being an operator-maintained duplicate of the
  ingress host.

### Negative Consequences

- A `platform_domains` schema change, migration, and API surface addition —
  larger than adding a manifest field alone.
- A portal host is fixed at install by the instance slug, and for Zitadel it is
  the OIDC issuer, so re-slugging later invalidates registered redirect URIs.
- Service portal hosts share the App hostname namespace, so an install can now
  fail with `hostname_conflict` where it previously could not.
- Portal order in a Service manifest is load-bearing: the first portal gets the
  bare host. Reordering portals in a registry change silently moves URLs.
- Portals and App routes diverge in exposure semantics (opt-in vs all domains),
  which must be documented or it reads as an inconsistency.
- Fresh installs declare portals that publish nowhere until an operator opts a
  domain in — good security default, extra setup step, and it depends on the
  unpublished state being clearly surfaced.
- Issue #61 becomes blocking rather than deferrable.

## Pros and Cons of the Options

### Host pattern: App-symmetric, first portal bare (chosen)

- Good, because the durable, user-visible host is named by the operator's
  instance slug rather than by the implementation, so `auth.<domain>` survives a
  Zitadel-to-Logto migration.
- Good, because it is exactly symmetric with App routes — one hostname rule to
  learn, one code path to maintain.
- Good, because it keeps Zitadel's pre-existing `zitadel.<domain>` host when
  installed under that slug.
- Bad, because Service hosts join the App hostname namespace, requiring an
  install-time cross-kind collision check.
- Bad, because it inherits the first-is-bare special case, so portal order in the
  manifest is load-bearing.

### Host pattern: always portal-prefixed

- Good, because App/Service hostname collision is unreachable by construction.
- Good, because no first-portal special case exists to get wrong.
- Bad, because it bakes the implementation name into the OIDC issuer
  (`console.zitadel.<domain>`), which is the single hardest thing to change later.
- Bad, because the portal name leaks into a URL where it reads wrong: an issuer is
  not a console.

### Host pattern: flat capability-style portal name

- Good, because it produces the nicest URL (`auth.<domain>`) with no operator
  action.
- Bad, because it is unimplementable with the current catalog: `zitadel` and
  `logto` both provide `oidc/oidc`, so both would declare portal `auth` and claim
  the same host, and could never coexist.
- Bad, because it asks the registry author to choose a globally unique role name
  without knowing what else is installed.

### Host pattern: reserved `svc` label

- Good, because collisions are impossible and infrastructure is self-evident.
- Bad, because it permanently reserves a second-level label from Apps.
- Bad, because hosts get longer for no functional gain over prefixing.

### Exposure: default-deny, opt-in per domain (chosen)

- Good, because declaring a portal never publishes it publicly.
- Good, because exposure is platform desired state, not manifest-author choice.
- Bad, because it costs a schema change, migration, and API surface.

### Exposure: default domain only

- Good, because it is the smallest safe change.
- Bad, because reaching a portal over a tunnel later needs another ADR.

### Exposure: per-portal `visibility`

- Good, because it touches no platform tables.
- Bad, because a community registry author could publish their own admin UI on a
  public domain — exposure policy belongs to the operator, not the manifest.

### Exposure: identical to App routes

- Good, because it is the least code and most symmetric.
- Bad, because ArcadeDB Studio lands on the public tunnel domain the moment it
  is configured.

### `external-host`: derive from portal (chosen)

- Good, because the platform is the single source of the host.
- Good, because issuer/ingress disagreement becomes unrepresentable.
- Bad, because it requires a new `MappingSource.kind`.

### `external-host`: manual, validated

- Good, because no new mapping kind is needed and drift fails closed.
- Bad, because it keeps a duplicated value that exists only to be checked.

### `external-host`: manual, unvalidated

- Bad, because a mismatch silently breaks OIDC issuer and redirect validation.

### Zitadel left on its provider-private ingress

- Good, because it is the fastest path to a reachable ArcadeDB Studio.
- Bad, because two ingress mechanisms coexist indefinitely and the divergence
  this ADR exists to remove survives in the one Service that most needs it.

## Links

- Amends [Ingress and Visibility Model](./20260517-ingress-and-visibility-model.md)
  — the Phase 1 "Service Admin Routes" clause.
- Builds on [Ingress Root Domain Configuration](./20260518-ingress-root-domain-configuration.md)
  — root domains as platform desired state, and its 2026-07-18 single-source
  amendment.
- Related to [Alpha Backbone Catalog and Service Providers](./20260622-alpha-backbone-catalog-and-service-providers.md)
  — the Zitadel and ArcadeDB Service entries this changes.
- Depends on issue #61 (route scheme derivation).

## Addendum 2026-08-01: the provisioning path was left behind

This ADR moved a Service's external identity to `spec.portals`, and the deploy
path followed: `providers/deployer._portal_mapping_value` derives the host from
the portal and feeds it to the provider. `core-registry` dropped the
`external-host`, `external-port`, and `external-secure` config options
accordingly.

The **binding-provisioning** path was not migrated. `provisioners/zitadel` kept
reading `external-host` from Service config, so once the option was gone every
OIDC binding blocked with `binding_provisioner_unavailable`. Nothing caught it:
no test covered a Service whose manifest had moved on, and the deploy path —
which had migrated — kept working. It surfaced only when a third-party App was
built against the platform and could not install.

Closed by deriving the same identity for provisioning.
`routing.service_portal_identity` returns the Service's **first** portal host
with the platform route port and scheme; `BindingProvisioningContext` carries it
as `service_portal`; the Zitadel provisioner reads it in preference to config.
The config fallback remains for a non-core Service that still declares those
options, and blocking now names both sources.

Deriving it in `routing` rather than beside the provisioner is deliberate: that
module already owns portal host derivation, and its opening comment explains why
one definition is what keeps the Ingress, the reported URL, and the runtime
mapping byte-identical. The provisioning identity is now the fourth reader of
that single derivation.

The lesson worth keeping: when a value moves from one source to another, its
consumers are not always in the same subsystem as its producer. Grep for the old
key across every layer, not just the one being edited.
