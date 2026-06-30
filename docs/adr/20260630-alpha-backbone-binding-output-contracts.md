# Alpha Backbone Binding Output Contracts

- Status: accepted
- Date: 2026-06-30
- Tags: alpha, backbone, bindings, secrets, seaweedfs, arcadedb, phase-1

Amends:

- `20260622-alpha-backbone-catalog-and-service-providers.md`

## Context and Problem Statement

The alpha backbone ADR accepted SeaweedFS and ArcadeDB as core Service providers
but explicitly left their app-scoped binding output fields unresolved. Publishing
core catalog entries and provider runtime wiring makes those fields a durable App
contract, because Apps map binding fields into runtime configuration and Nephos
materializes them into App-side Kubernetes Secrets.

Without an accepted output contract, implementation notes, catalog README files,
and `.agents/context` guidance can drift and future Apps may depend on
conflicting Secret keys.

## Decision

SeaweedFS S3 app-scoped bindings materialize these App-side Secret keys:

```text
endpointUrl
bucket
accessKeyId
secretAccessKey
region
```

ArcadeDB app-scoped bindings materialize these App-side Secret keys for every
enabled protocol:

```text
host
port
database
username
password
protocol
uri
```

The accepted ArcadeDB core app-scoped provisioning protocols are:

```text
sql/arcadedb
opencypher/bolt
opencypher/n4j
```

ArcadeDB `gremlin/gremlin` and `mongo/mongo` remain catalog-visible optional
runtime surfaces, but app-scoped provisioning for them is disabled by default
until explicitly enabled and verified.

Binding Secret values remain sensitive. API/status/repository summaries must
report only redacted output metadata such as target, Secret name, namespace, key
names, capability, protocol, and `redacted: true`.

## Consequences

The unresolved-output statement in the alpha backbone ADR is superseded for
SeaweedFS and ArcadeDB by this ADR. Zitadel output fields remain governed by the
Zitadel provisioning plan and any later ADR that promotes those fields as a
public contract.

Core-registry Service READMEs may document these keys as canonical for Phase 1.

Nephos provider/runtime code must not report a SeaweedFS Service as wired to
configured S3 credentials unless the SeaweedFS pod actually consumes the
configured credentials.

## Non-Goals

- Do not implement live SeaweedFS bucket/user provisioning in this ADR.
- Do not implement live ArcadeDB database/user provisioning in this ADR.
- Do not promote canonical JSON schemas or examples under `schemas/` or
  `examples/`.
- Do not define `dev` or `prd` secret-manager policy.
