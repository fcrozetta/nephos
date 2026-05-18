# Naming, Slug, and Runtime Metadata Conventions

- Status: accepted
- Date: 2026-05-18
- Tags: naming, metadata, kubernetes, manifests, phase-1

## Context and Problem Statement

Nephos derives Kubernetes namespaces, binding Secret names, route identity, and runtime metadata from Nephos platform names.

The system needs predictable naming rules so reconciliation, debugging, drift detection, and cleanup do not depend on ad hoc string rewriting.

## Decision

Use strict DNS-label style machine identifiers for:

- manifest `metadata.name`
- App requirement binding aliases
- route names
- installed App instance slugs
- installed Service instance slugs
- catalog entry slugs

Accepted machine identifier shape:

```text
^[a-z0-9]([-a-z0-9]*[a-z0-9])?$
```

Identifiers must use lowercase ASCII letters, digits, and hyphens.

Identifiers must start and end with an alphanumeric character.

Nephos rejects invalid machine identifiers.

Nephos does not silently normalize, lowercase, truncate, or suffix invalid identifiers.

## Instance Names

By default, an installed instance name equals the catalog manifest `metadata.name`.

Users may provide an explicit instance name at install time.

App instance names are unique within the App instance scope.

Service instance names are unique within the Service instance scope.

An App instance and Service instance may use the same base name because their runtime namespaces are prefixed differently:

- `app-<slug>`
- `svc-<slug>`

## Collision Handling

If a name, alias, route, provider, or instance selection collides or is ambiguous, Nephos fails and requires explicit user input.

Nephos does not silently add suffixes such as `-2`.

Nephos does not generate random suffixes for platform-visible names in Phase 1.

## Length Limits

Generated Kubernetes object names must fit Kubernetes name limits.

Known Phase 1 derived names:

- App namespace: `app-<slug>`
- Service namespace: `svc-<slug>`
- App binding Secret: `nephos-bind-<alias>`

Prefixes count toward the final Kubernetes name length.

If a final generated name would exceed the Kubernetes limit for that resource, Nephos rejects the input and asks for a shorter explicit name or alias.

Nephos does not truncate long names.

## Runtime Labels and Annotations

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

Binding Secrets must carry:

```yaml
app.kubernetes.io/managed-by: nephos
nephos.pro/app-instance: <app-instance>
nephos.pro/service-instance: <service-instance>
nephos.pro/capability: <capability>
nephos.pro/binding-alias: <alias>
```

Use labels where Kubernetes label constraints are satisfied.

Use annotations for future metadata that does not fit label constraints or should not be selector-oriented.

## Owner References

Nephos does not use Kubernetes `ownerReferences` to represent Nephos platform relationships in Phase 1.

Nephos desired state in the API/database is the source of truth.

Kubernetes labels and annotations exist for inspection, drift detection, and cleanup.

Do not model App-Service bindings, Service dependents, lifecycle ownership, or desired-state ownership through Kubernetes owner references.

Helm charts or Kubernetes controllers may create their own internal owner references as runtime implementation details, but Nephos must not rely on those references as the platform relationship model.

## Consequences

Names are boring and predictable.

Users must fix invalid names explicitly instead of relying on hidden normalization.

The model avoids drift between user-visible platform identity and Kubernetes object identity.

Rejecting collisions keeps ambiguous installs and bindings from creating accidental infrastructure.

The lack of Nephos-owned `ownerReferences` preserves the boundary:

```text
intent -> desired state -> reconcile into Kubernetes
```

## Open Questions

Need to decide later:

- exact metadata for non-Secret runtime objects beyond the accepted Phase 1 keys
- whether annotations should duplicate relationship labels for easier manual inspection
- whether future remote catalog entries need publisher/source identity labels
