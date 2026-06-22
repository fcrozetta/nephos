# Alpha Backbone Catalog and Service Providers

- Status: accepted
- Date: 2026-06-22
- Tags: alpha, catalog, services, capabilities, protocols, providers, pulumi, auth, phase-1

Amends:

- `20260517-services-as-capability-providers.md`
- `20260517-binding-model.md`
- `20260517-auth-and-user-model.md`
- `20260517-phase-1-scope.md`
- `20260517-app-and-service-package-format.md`
- `20260518-catalog-and-manifest-loading.md`
- `20260518-service-operation-contract-boundary.md`
- `20260523-api-0-0-1-internal-provisioning-handlers.md`
- `20260529-pulumi-provider-boundary.md`

## Context and Problem Statement

Nephos has proved the API/runtime path with PostgreSQL and a reference App.
The alpha backbone now needs a concrete Service catalog scope and protocol-aware
binding model before implementation expands to identity, object storage, and
graph/document database Services.

Capability-only matching is too coarse for databases. For example, `sql` alone
does not distinguish PostgreSQL SQL from ArcadeDB SQL, and broad database
categories do not identify the client protocol an App can actually use.

## Decision

The Nephos alpha backbone Service order is:

1. PostgreSQL
2. Zitadel
3. SeaweedFS
4. ArcadeDB
5. the first dogfood App that proves real local bindings against those Services

Pulumi is the runtime path for the alpha backbone.

Do not introduce Aspire.

Helm may be used underneath Pulumi-backed Service providers when a chart is the
easiest Service install path, but Helm charts do not define Nephos Service
behavior.

Service behavior remains Nephos-owned provider code:

- install, start, stop, remove, destroy
- status and redacted evidence
- app-scoped binding provisioning
- app-scoped binding deprovisioning
- Service surfaces
- future maintenance operations

Zitadel is modeled as a Service only.

Zitadel login and admin UI are Service surfaces/routes. They are not a separate
App and do not create an App dependency edge.

Database and infrastructure bindings match on:

```text
capability + protocol
```

Catalog App requirements and Service provisions must carry both fields where a
protocol is meaningful.

Accepted initial alpha backbone provisions:

| Service | Capability | Protocol | Notes |
| --- | --- | --- | --- |
| PostgreSQL | `sql` | `postgres` | App-scoped database/user credentials |
| ArcadeDB | `sql` | `arcadedb` | ArcadeDB SQL over its accepted client path |
| ArcadeDB | `opencypher` | `bolt` | OpenCypher over Bolt |
| ArcadeDB | `opencypher` | `n4j` | OpenCypher over ArcadeDB HTTP/Neo4j-compatible style |
| ArcadeDB | `gremlin` | `gremlin` | Optional, only when enabled |
| ArcadeDB | `mongo` | `mongo` | Optional, only when enabled |
| SeaweedFS | `object-storage` | `s3` | App-scoped bucket/access credentials |
| Zitadel | `oidc` | `oidc` | Per-App OIDC client material |
| Zitadel | `service-account` | `jwt` | Per-App service account/JWT material |

Capability names should describe the product-level feature. Protocol names
should describe the concrete client wire/API contract an App can use.

The older examples that used `postgres` as a standalone capability are
superseded for alpha backbone catalog matching by `sql/postgres`.

## Binding Resolution Rule

An App requirement is eligible for a Service provision only when both the
capability and protocol match.

If no installed running Service instance provides the requested
`capability + protocol`, binding reconciliation is blocked.

If more than one installed running Service instance provides the requested
`capability + protocol`, App installation or binding reconciliation requires
explicit provider selection.

Aliases remain App-local binding names. They are not substitutes for protocol
matching.

## Service Surface Rule

A Service surface is a browser or network surface exposed by a Service instance
for that Service's own management, login, API, or protocol needs.

Service surfaces are not Apps.

Zitadel's login/admin UI is the first accepted Service-surface use case.

Generic Service admin route exposure remains out of scope until a later
decision. This ADR accepts only the narrow Zitadel Service-surface need for the
alpha backbone.

## Consequences

The catalog manifest model needs protocol-aware `requires` and `provides`
entries before new backbone manifests become canonical.

The API/database binding model and response summaries need to preserve protocol
alongside capability when implementation catches up.

Service provider dispatch must select provisioning behavior by
`capability + protocol`, not capability alone.

PostgreSQL provisioning remains the first concrete `sql/postgres` provider path.

SeaweedFS, ArcadeDB, and Zitadel binding output fields are not finalized by this
ADR. They require implementation plans or follow-up ADR/context updates before
canonical schemas or examples are promoted.

The Phase 1 "no Service admin routes through Nephos ingress" line is narrowed:
generic Service admin routes are still out of scope, but Zitadel Service
surfaces/routes are accepted for the alpha backbone.

## Non-Goals

- Do not add Aspire.
- Do not expose Pulumi or Helm as the product model.
- Do not make Helm charts define Nephos Service behavior.
- Do not add canonical schemas under `schemas/`.
- Do not add canonical examples under `examples/`.
- Do not implement runtime code in this decision slice.
- Do not design a general Service-surface routing system beyond the Zitadel
  alpha need.
- Do not finalize non-PostgreSQL binding output field schemas in this ADR.
