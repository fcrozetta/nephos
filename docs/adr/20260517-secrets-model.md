# Secrets Model

- Status: accepted
- Date: 2026-05-17
- Tags: secrets, security, kubernetes, bindings, phase-1

## Context and Problem Statement

Nephos needs a secrets model for credentials created during App-Service binding and Service provisioning.

Initial implementation needs to be simple, but future integrations should remain possible.

## Decision

Use Kubernetes Secrets for Phase 1.

External secret managers are deferred.

Future external secret integration may be modeled through Services or adapters, but it is not Phase 1 scope.

Possible future providers:

- Vault
- 1Password
- SOPS
- Infisical
- other external secret managers

Fer expects a future secret manager such as Infisical to be modeled as a Service if it becomes part of the platform.

Nephos owns secret policy, naming intent, labels, injection behavior, preservation behavior, deletion behavior, and redaction rules.

Kubernetes owns the concrete Secret resources in Phase 1.

## Namespace Placement

Service-internal and Service-admin secrets live in the Service instance namespace.

App binding credentials are materialized into the App namespace.

Do not require Apps to read Secrets across namespace boundaries.

Bindings are the source of truth for which App may receive which Service credentials.

Service manifests declare logical binding outputs, not final consuming Secret names.

Nephos chooses deterministic Secret names from binding alias.

For `app-secret`, the Secret is created in the consuming App namespace with this name:

```text
nephos-bind-<alias>
```

The alias must follow the accepted Nephos machine identifier rule.

If `nephos-bind-<alias>` would exceed Kubernetes Secret name limits, Nephos rejects the alias and requires a shorter explicit alias.

For Phase 1, `app-secret` is the only accepted binding output target.

For PostgreSQL `app-secret` outputs, use these exact lowercase Kubernetes Secret keys:

- `host`
- `port`
- `database`
- `username`
- `password`
- `uri`

Runtime mappings may translate these keys into chart values or environment variables later.

## Binding Secret Metadata

Binding Secrets must include metadata that identifies:

- App instance
- Service instance
- capability
- binding alias

Accepted Phase 1 metadata keys:

```yaml
app.kubernetes.io/managed-by: nephos
nephos.pro/app-instance: <app-instance>
nephos.pro/service-instance: <service-instance>
nephos.pro/capability: <capability>
nephos.pro/binding-alias: <alias>
```

Rebinding an alias to a different Service instance updates the same Secret name with new contents after explicit reconciliation or confirmation.

Rebinding does not create a new Secret name by default.

## Lifecycle Behavior

Stop preserves Secrets.

Remove preserves Secrets.

Destroy deletes Secrets created for the destroyed entity after destructive confirmation when persistent data or credentials are involved.

This follows the broader lifecycle model:

- stop is temporary
- remove removes deployed runtime objects while preserving durable state and metadata
- destroy is the destructive cleanup operation

## Redaction

Secret values must be redacted in API responses, CLI output, status output, logs, and diagnostics by default.

Do not expose secret values unless a future explicit reveal command is designed and accepted.

## Nephos Responsibilities

Nephos owns the policy of:

- what secrets are created
- where secrets are stored
- how secrets are labeled
- how secrets are injected
- how secrets are rotated
- what is preserved on stop/remove/destroy
- what is redacted in user-facing output

## Open Questions

Need to define:

- rotation behavior
- whether secrets are backed up
- future reveal/debug command behavior
- external secret manager integration model
- non-PostgreSQL Secret key serialization
- binding credential materialization schemas beyond accepted PostgreSQL logical fields

## Consequences

Kubernetes Secrets are simple and match the Phase 1 K3s target.

They are not a complete secret management system.

Nephos must avoid pretending Kubernetes Secrets provide rotation, external vaulting, or advanced audit guarantees.

Materializing binding credentials into App namespaces avoids cross-namespace Secret access, but Nephos must own the copy/update/delete semantics.

## Status Notes

Do not make Apps depend on direct access to Service namespace Secrets.

Do not hardcode secret conventions without documenting them.
