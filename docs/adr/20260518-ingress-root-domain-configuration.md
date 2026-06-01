# Ingress Root Domain Configuration

- Status: accepted
- Date: 2026-05-18
- Tags: ingress, configuration, desired-state, cli, api, phase-1

## Context and Problem Statement

Nephos route manifests describe route intent, not final hostnames.

Phase 1 supports multiple ingress root domains with one default/canonical domain, but the source of that domain configuration must be defined.

## Decision

Ingress root domains are platform desired state in the Nephos API/database.

They are not App manifest fields.

They are not startup-only environment variables.

They are not local config files that bypass the canonical desired-state model.

Nephos API and CLI manage ingress root domains through platform configuration operations.

The accepted HTTP API path is `/platform/config/domains`.

The exact CLI command spelling remains open.

## Configuration Shape

Use this semantic shape:

```yaml
rootDomains:
  - name: local
    domain: nephos.local
    default: true
  - name: cloudflare
    domain: nephos.fcrozetta.app
```

Rules:

- `name` is a Nephos machine identifier.
- `domain` is a DNS suffix.
- exactly one root domain has `default: true`.
- at least one root domain is required before route reconciliation can generate hosts.

## Domain Validation

Store only DNS suffixes.

Accept examples:

- `nephos.local`
- `nephos.fcrozetta.app`

Reject:

- full URLs such as `https://nephos.local`
- paths such as `nephos.local/apps`
- wildcards such as `*.nephos.local`
- schemes
- ports

The wildcard belongs in DNS, tunnel, or external routing configuration, not in Nephos root domain state.

## Operations

Phase 1 needs platform configuration operations for:

- add root domain
- list root domains
- remove root domain
- set default root domain

Accepted API path:

```text
/platform/config/domains
```

Accepted API operations:

```text
GET /platform/config/domains
POST /platform/config/domains
POST /platform/config/domains/{name}/actions/set-default
POST /platform/config/domains/{name}/actions/remove
```

The action endpoints follow the API 0.0.1 mutation envelope pattern and create
reconciliation requests rather than mutating runtime ingress inline.

Removing a root domain removes that domain's generated host aliases from reconciled ingress after explicit confirmation when existing routes use it.

Removing a non-default root domain does not remove route intent or Apps.

Removing the default root domain requires selecting another default first or performing a single operation that both removes it and selects a replacement.

Nephos must not leave zero root domains after initial setup if any installed App route depends on generated hostnames.

## Initial Setup

Nephos setup must create the initial platform configuration before Apps are installed.

That initial setup includes at least one ingress root domain and exactly one default/canonical root domain.

The root domain may be provided by the user during setup.

For API 0.0.1 backend-local development, `uv run nephos-api init` creates the
initial internal root domain. If no domain is provided, it defaults to
`nephos.local` with platform-domain name `internal`.

`NEPHOS_API_INTERNAL_DOMAIN` may supply that initial domain from `.env` or the
process environment.

For local browser testing without editing `/etc/hosts`, use a DNS suffix that
already resolves to the ingress endpoint, such as `nephos.localhost`. Traefik
or another ingress controller routes HTTP after the hostname resolves; it does
not provide local DNS resolution for `*.nephos.local`.

The selected runtime Ingress class is not a platform root-domain field.
API 0.0.1 may set generated Kubernetes `ingressClassName` from
`NEPHOS_API_INGRESS_CLASS` or by auto-detecting a single/default cluster
`IngressClass`.

The later user-facing setup UX belongs in the separate `nephos-cli` repository.

Nephos setup command design is deferred until after Nephos API `0.0.1` is implemented.

Do not rely on App installation to discover or create ingress root domain configuration.

Do not silently invent hostnames during App install.

The backend may start with an empty database.

When required platform configuration is missing, the backend reports platform configuration as incomplete until setup creates the required desired state.

## Status Output

App status should show:

- canonical URL generated from the default root domain
- aliases generated from non-default root domains

Example:

```text
canonical: http://paperless.nephos.local
aliases:
  - http://paperless.nephos.fcrozetta.app
```

Because Phase 1 Nephos-managed ingress is HTTP-only, Nephos-generated URLs use `http://`.

User-managed systems such as Cloudflare Tunnel may expose the same host through HTTPS outside Nephos.

## Consequences

Ingress domain state follows the accepted source-of-truth model.

App manifests stay portable because they declare route intent instead of hostnames.

Manual Cloudflare Tunnel remains compatible because Nephos only needs host rules; DNS, tunnel routing, and TLS termination stay user-managed.

Initial setup has one more required configuration step, but App install behavior becomes deterministic.

## Open Questions

Need to decide later:

- exact CLI command spelling
- whether setup is interactive, flag-driven, or both
- exact setup command spelling in `nephos-cli`
- setup idempotency behavior
- App install behavior when setup is missing
- whether route status should show HTTP-only Nephos URLs, externally observed HTTPS URLs, or both after future tunnel/DNS integrations
