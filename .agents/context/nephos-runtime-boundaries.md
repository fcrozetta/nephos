# Nephos Runtime Boundaries

## Namespace Model

Nephos uses separate Kubernetes namespaces for control-plane components, App instances, and Service instances.

Namespace pattern:

- `nephos-system` for Nephos control-plane/runtime support components
- `app-<slug>` for an App instance
- `svc-<slug>` for a Service instance

Slugs use strict DNS-label style machine identifiers:

```text
^[a-z0-9]([-a-z0-9]*[a-z0-9])?$
```

Nephos rejects invalid slugs instead of silently normalizing them.

By default, an installed instance name equals the catalog manifest `metadata.name`.

Users may provide an explicit instance name at install time.

App instance names are unique within the App instance scope.

Service instance names are unique within the Service instance scope.

If a namespace name would exceed Kubernetes limits after adding `app-` or `svc-`, Nephos rejects the name and requires a shorter explicit instance name.

Nephos does not silently truncate, suffix, or randomize namespace names.

Apps and Services do not share a namespace by default.

Shared Service instances live in Service namespaces even when multiple Apps bind to them.

Dedicated Service instances are still Service instances and also live in Service namespaces.

`remove` preserves namespaces.

`destroy` deletes namespaces by default after destructive confirmation when persistent data exists.

Phase 1 does not apply default-deny NetworkPolicy.

Network policy is reserved for later design.

## Runtime Metadata

Nephos-managed Kubernetes resources should use:

```yaml
app.kubernetes.io/managed-by: nephos
```

Nephos-owned relationship metadata uses keys under:

```text
nephos.pro/*
```

Accepted Phase 1 keys:

- `nephos.pro/app-instance`
- `nephos.pro/service-instance`
- `nephos.pro/capability`
- `nephos.pro/binding-alias`

Nephos does not use Kubernetes `ownerReferences` to represent App-Service bindings, Service dependents, lifecycle ownership, or desired-state ownership in Phase 1.

Nephos desired state in the API/database is the source of truth.

## Ingress Model

Traefik is the Phase 1 default ingress controller because K3s includes it by default.

Nephos owns route and visibility intent.

Kubernetes owns concrete Ingress resources.

Do not expose raw Kubernetes Ingress configuration as the primary Nephos UX.

Phase 1 implements `local` visibility.

Reserved future visibility modes:

- `private`
- `public`
- `tailnet`

Cloudflare Tunnel, Tailscale, public DNS automation, and cert-manager/TLS automation are deferred.

Nephos-generated local ingress must still be compatible with a manually configured Cloudflare Tunnel.

Practical Phase 1 constraint:

- the user may manually point a wildcard or subdomain such as `*.nephos.fcrozetta.app` at the cluster ingress
- Nephos should not require a different product model for that to work
- Nephos does not manage Cloudflare credentials, tunnel lifecycle, or DNS automation in Phase 1

Phase 1 supports multiple configured ingress root domains.

Exactly one configured root domain is the default/canonical domain.

At least one root domain is required for generated route hosts.

Nephos generates host rules for each configured root domain.

Root domains are aliases for the same Nephos route intent.

They do not create separate Apps, separate routes, or separate bindings.

Ingress root domains are platform desired state in the Nephos API/database.

They are managed through Nephos API/CLI platform configuration operations.

They are not App manifest fields.

Semantic shape:

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

Phase 1 Nephos-managed ingress is HTTP-only.

TLS automation, cert-manager integration, and user-provided TLS Secret support are deferred.

User-managed systems such as Cloudflare Tunnel may terminate TLS outside Nephos.

If generated hostnames collide, Nephos fails and requires an explicit route, App instance, or domain policy change.

Services do not expose admin routes through Nephos ingress in Phase 1.

Service management stays through Nephos API/CLI operations and future typed Service operations.

Phase 1 root domain operations:

- add root domain
- list root domains
- remove root domain
- set default root domain

Accepted API path:

```text
/platform/config/domains
```

The exact CLI command spelling remains open.

Removing a root domain removes that domain's generated host aliases from reconciled ingress after explicit confirmation when existing routes use it.

Nephos setup must create the initial platform configuration before Apps are installed.

That setup includes at least one ingress root domain and exactly one default/canonical root domain.

The setup UX and command implementation belong in the separate `nephos-cli` repository after Nephos API `0.0.1` is implemented.

The backend may start with an empty database and report platform configuration as incomplete until setup creates required desired state.

Do not rely on App installation to discover or create ingress root domain configuration.

Stopping an App keeps route intent.

Stopped Apps may keep runtime ingress objects, but status must report the App as stopped or unavailable.

Removing an App removes runtime ingress objects.

Destroying an App removes runtime ingress objects and persistent data according to lifecycle semantics.

## Secrets Model

Phase 1 uses Kubernetes Secrets.

External secret managers are deferred.

A future secret manager such as Infisical may be modeled as a Service if it becomes part of the platform.

Nephos owns secret policy:

- what secrets are created
- where secrets are stored
- how secrets are labeled
- how secrets are injected
- how binding credentials are materialized
- what is preserved on stop/remove
- what is deleted on destroy
- what is redacted in output

Service-internal and Service-admin secrets live in the Service instance namespace.

App binding credentials are materialized into the App namespace.

Apps should not read Service namespace Secrets directly.

Bindings are the source of truth for which App may receive which Service credentials.

Service manifests declare logical binding outputs, not final consuming Secret names.

Nephos chooses deterministic Secret names from binding alias.

For `app-secret`, Nephos creates the Secret in the consuming App namespace with this name:

```text
nephos-bind-<alias>
```

The alias must follow the accepted Nephos machine identifier rule.

If `nephos-bind-<alias>` would exceed Kubernetes Secret name limits, Nephos rejects the alias and requires a shorter explicit alias.

Binding Secrets include:

```yaml
app.kubernetes.io/managed-by: nephos
nephos.pro/app-instance: <app-instance>
nephos.pro/service-instance: <service-instance>
nephos.pro/capability: <capability>
nephos.pro/binding-alias: <alias>
```

Rebinding an alias to a different Service instance updates the same Secret name with new contents after explicit reconciliation or confirmation.

For Phase 1, the only accepted binding output target is `app-secret`.

For PostgreSQL `app-secret` outputs, use exact lowercase Kubernetes Secret keys:

- `host`
- `port`
- `database`
- `username`
- `password`
- `uri`

Stop preserves Secrets.

Remove preserves Secrets.

Destroy deletes Secrets created for the destroyed entity after destructive confirmation when persistent data or credentials are involved.

Secret values must be redacted in API responses, CLI output, status output, logs, and diagnostics by default.

Do not expose secret values unless a future explicit reveal command is designed and accepted.

## Still Open

- exact CLI command spelling for root domain operations
- whether setup is interactive, flag-driven, or both
- exact setup command spelling in `nephos-cli`
- setup idempotency behavior
- App install behavior when setup is missing
- secret rotation behavior
- whether/how secrets participate in backup
- non-PostgreSQL Secret key serialization
