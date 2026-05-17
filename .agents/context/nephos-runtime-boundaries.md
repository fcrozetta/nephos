# Nephos Runtime Boundaries

## Namespace Model

Nephos uses separate Kubernetes namespaces for control-plane components, App instances, and Service instances.

Namespace pattern:

- `nephos-system` for Nephos control-plane/runtime support components
- `app-<slug>` for an App instance
- `svc-<slug>` for a Service instance

Apps and Services do not share a namespace by default.

Shared Service instances live in Service namespaces even when multiple Apps bind to them.

Dedicated Service instances are still Service instances and also live in Service namespaces.

`remove` preserves namespaces.

`destroy` deletes namespaces by default after destructive confirmation when persistent data exists.

Phase 1 does not apply default-deny NetworkPolicy.

Network policy is reserved for later design.

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

Nephos chooses deterministic Secret names from binding identity.

The exact naming algorithm remains open.

For Phase 1, the only accepted binding output target is `app-secret`.

Stop preserves Secrets.

Remove preserves Secrets.

Destroy deletes Secrets created for the destroyed entity after destructive confirmation when persistent data or credentials are involved.

Secret values must be redacted in API responses, CLI output, status output, logs, and diagnostics by default.

Do not expose secret values unless a future explicit reveal command is designed and accepted.

## Still Open

- exact slug normalization and collision handling
- exact namespace labels and annotations
- exact default local hostname/domain policy
- wildcard domain behavior
- TLS and cert-manager strategy
- route collision handling
- whether Services can expose admin routes
- binding Secret naming algorithm
- secret labels and annotations
- secret rotation behavior
- whether/how secrets participate in backup
- exact Secret key serialization
