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

The exact HTTP API path and CLI command spelling remain open.

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

Removing a root domain removes that domain's generated host aliases from reconciled ingress after explicit confirmation when existing routes use it.

Removing a non-default root domain does not remove route intent or Apps.

Removing the default root domain requires selecting another default first or performing a single operation that both removes it and selects a replacement.

Nephos must not leave zero root domains after initial setup if any installed App route depends on generated hostnames.

## Initial Setup

Nephos setup must create the initial platform configuration before Apps are installed.

That initial setup includes at least one ingress root domain and exactly one default/canonical root domain.

The root domain may be provided by the user during setup.

Do not rely on App installation to discover or create ingress root domain configuration.

Do not silently invent hostnames during App install.

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

- exact API path
- exact CLI command spelling
- whether setup is interactive, flag-driven, or both
- whether route status should show HTTP-only Nephos URLs, externally observed HTTPS URLs, or both after future tunnel/DNS integrations
