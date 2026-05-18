# Ingress and Visibility Model

- Status: accepted
- Date: 2026-05-17
- Tags: ingress, networking, traefik, visibility, phase-1

## Context and Problem Statement

Nephos needs to expose Apps and possibly some Services through routes.

Ingress behavior must support local-first infrastructure while allowing public/private/tailnet modes later.

K3s commonly includes Traefik, making it a practical default.

## Decision

Use Traefik as the Phase 1 default ingress controller because K3s includes Traefik by default.

Nephos owns ingress intent.

Kubernetes owns ingress resources.

Nephos should generate and reconcile Kubernetes Ingress resources from Nephos route intent, but raw Ingress YAML must not become the primary Nephos UX.

## Visibility Modes

Phase 1 implements:

- local

Reserve these visibility modes for later:

- private
- public
- tailnet

`local` means the route is intended for the local/self-hosted environment and the user-controlled network path around it.

Phase 1 does not automate public DNS, Cloudflare Tunnel, Tailscale, tailnet exposure, or certificate management.

However, Nephos-generated local ingress must be compatible with a manually configured Cloudflare Tunnel or equivalent user-managed tunnel.

The practical requirement is:

- Fer may start/configure Cloudflare Tunnel manually
- the tunnel may route a wildcard or subdomain such as `*.nephos.fcrozetta.app` to the cluster ingress
- Nephos should not require a different ingress model for that to work
- Nephos does not manage Cloudflare credentials, tunnel lifecycle, or DNS automation in Phase 1

## Root Domains And Hostnames

Phase 1 supports multiple configured ingress root domains.

Exactly one configured root domain is the default/canonical domain.

At least one root domain is required for generated route hosts.

Nephos generates host rules for each configured root domain.

Root domains are aliases for the same Nephos route intent.

They do not create separate Apps, separate routes, or separate bindings.

Ingress root domains are platform desired state in the Nephos API/database.

They are managed through Nephos API/CLI platform configuration operations.

They are not App manifest fields.

Semantic configuration shape:

```yaml
rootDomains:
  - name: local
    domain: nephos.local
    default: true
  - name: cloudflare
    domain: nephos.fcrozetta.app
```

`name` is a Nephos machine identifier.

`domain` is a DNS suffix.

Store only suffixes such as `nephos.local`, not URLs, paths, wildcards, schemes, or ports.

Example root domains:

- `nephos.local`
- `nephos.fcrozetta.app`

Default route host pattern:

```text
<app-instance>.<root-domain>
```

Non-default route host pattern:

```text
<route>.<app-instance>.<root-domain>
```

Example:

- `paperless.nephos.local`
- `paperless.nephos.fcrozetta.app`
- `api.paperless.nephos.local`
- `api.paperless.nephos.fcrozetta.app`

Status should identify the canonical URL and may list aliases.

App status should show the canonical URL from the default root domain and aliases from non-default root domains.

Avoid path-based App routing in Phase 1.

Do not require Apps to run under paths such as `/paperless`.

Many self-hosted Apps assume host-root deployment or need app-specific base path support.

## TLS

Phase 1 Nephos-managed ingress is HTTP-only.

TLS automation, cert-manager integration, and user-provided TLS Secret support are deferred.

User-managed systems such as Cloudflare Tunnel may terminate TLS outside Nephos.

Nephos does not manage Cloudflare credentials, tunnel lifecycle, DNS records, TLS certificates, or certificate renewal in Phase 1.

## Collision Behavior

If generated hostnames collide, Nephos fails and requires an explicit route, App instance, or domain policy change.

Nephos does not suffix, randomize, or silently override hostnames.

## Service Admin Routes

Services do not expose admin routes through Nephos ingress in Phase 1.

Service management stays through Nephos API/CLI operations and future typed Service operations.

## Root Domain Operations

Phase 1 needs platform configuration operations for:

- add root domain
- list root domains
- remove root domain
- set default root domain

The exact HTTP API path and CLI command spelling remain open.

Removing a root domain removes that domain's generated host aliases from reconciled ingress after explicit confirmation when existing routes use it.

Removing a non-default root domain does not remove route intent or Apps.

Removing the default root domain requires selecting another default first or performing a single operation that both removes it and selects a replacement.

## Initial Setup

Nephos setup must create the initial platform configuration before Apps are installed.

That initial setup includes at least one ingress root domain and exactly one default/canonical root domain.

Do not rely on App installation to discover or create ingress root domain configuration.

Do not silently invent hostnames during App install.

## Stopped And Removed Apps

Stopping an App keeps route intent.

In Phase 1, stopped Apps may keep runtime ingress objects.

Status should report that the App is stopped or unavailable rather than pretending the route is healthy.

Removing an App removes runtime ingress objects.

Destroying an App removes runtime ingress objects and persistent data according to lifecycle semantics.

## Nephos Responsibilities

Nephos should manage:

- route intent
- visibility mode
- ingress metadata
- user-facing URL/status
- public/private/tailnet distinction
- integration hooks for DNS/tunnels later

## Open Questions

Need to define:

- future Cloudflare integration
- future Tailscale integration
- exact API path and CLI command spelling for root domain operations
- whether setup is interactive, flag-driven, or both

## Consequences

Traefik is a pragmatic default for K3s and avoids making ingress controller selection a Phase 1 product surface.

The visibility model gives Nephos room to add public, private, and tailnet exposure later without turning Phase 1 into tunnel/DNS automation.

Keeping stopped App ingress avoids losing temporary route intent during stop/start cycles, but status must make the stopped state explicit.

## Status Notes

Do not make Cloudflare Tunnel or Tailscale foundational in Phase 1.

Do not leak raw ingress configuration as the primary product UX.
