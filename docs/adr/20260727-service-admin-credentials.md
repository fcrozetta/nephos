# Service admin credentials in the manifest

- Status: accepted
- Date: 2026-07-27
- Tags: catalog, manifest-schema, secrets, console, usability

Technical Story: follow-on to ADR 20260726 (authenticated secret reveal). Reveal
returns a password without naming the account it opens, which is not enough to
sign in.

## Context and Problem Statement

ADR 20260726 gave an operator a way to read a credential Nephos generated for
them. It did not give them the other half. For PostgreSQL the operator chose
neither half: the password is generated, and the username `postgres` is
hardcoded in the runtime provider (`POSTGRES_USER`), reaching no manifest and
therefore no catalog, no API payload, and no console.

The same is true of ArcadeDB, whose `root` account exists only inside a
`-Darcadedb.server.rootPassword` argument in the provider. Zitadel is the
exception: it already models `admin-username` as a config option, so the console
renders it today as ordinary non-secret config.

So the platform could show a password while being structurally unable to say
which account it belonged to. Reading the username out of provider code into the
console was rejected outright: wrong repository, and it would drift from the
provider silently.

Where should a Service's own admin login identity be declared?

## Decision Drivers

- An operator must be able to sign in using only what Nephos tells them.
- The username is not a secret and must not be treated as one; withholding it was
  the defect.
- Cover Services with no browser surface. PostgreSQL has no portal, and `psql`
  still needs a username.
- Keep the password flowing through the existing redaction and reveal paths
  rather than duplicating it into a second field.
- No per-service knowledge in the console.

## Considered Options

- a `credentials` block on `ServiceSpec`
- credentials declared per portal
- add an `admin-username` config option to each Service, mirroring Zitadel
- leave it unmodelled and document `kubectl`

## Decision Outcome

Chosen: **a `credentials` block on `ServiceSpec`.**

```yaml
spec:
  credentials:
    username: postgres          # fixed by the runtime
    passwordOption: admin-password
```

```yaml
spec:
  credentials:
    usernameOption: admin-username   # chosen by the operator at install
    passwordOption: admin-password
```

- Exactly one of `username` or `usernameOption`, enforced by a model validator.
  `username` is for an identity the runtime imposes and the operator cannot
  change; `usernameOption` points at a config option when they choose it.
- `passwordOption` names the config option holding the secret rather than
  inlining a value, so the password keeps flowing through redaction and the
  reveal endpoint instead of gaining a second, unprotected path.
- The Service payload resolves the username from *instance* config, so it
  reflects what was installed rather than a registry default. Zitadel installed
  as `auth` reports `root@auth.nephos.lcl`, not the manifest's placeholder.
- The username is returned in clear text. It is an account name, and hiding it is
  the problem this ADR exists to fix.

### Validation

A `credentials` block naming an option that is not declared is rejected at
catalog load. So is a `passwordOption` the API would not treat as sensitive:
otherwise a manifest could declare a credential that the config payload prints in
clear text and the reveal endpoint simultaneously refuses to serve, contradicting
itself in both directions.

The sensitivity predicate moves to `catalog.py` as `is_sensitive_config_name` and
is shared by redaction, the reveal gate, and this validation. Three copies of
that rule could drift apart silently; one cannot.

### Service-scoped, not portal-scoped

Portal-scoped credentials read more naturally ("how to log into this surface")
and were the initial instinct. They cannot express PostgreSQL, which has no
portal and still needs a username for `psql`, so the platform would have covered
the case with a UI and missed the case without one. A Service has exactly one
admin identity regardless of how many surfaces it exposes, so the Service is the
right scope.

### Positive Consequences

- The console can show a complete login: username plus a reveal for the password.
- Provider-internal knowledge becomes a declared contract, reviewable in the
  registry rather than buried in a container argument.
- The password gains no second path; it stays behind the existing gate.
- Services with no browser surface are covered.

### Negative Consequences

- One admin identity per Service. A Service with genuinely distinct per-surface
  logins cannot express that, and would need portal-scoped credentials after all.
- `username` as a literal duplicates a value the provider also hardcodes. Nothing
  enforces that they agree, so a provider change can silently make the manifest
  lie. A runtime mapping (`kind: credentials`) could close that later.
- Yet another manifest field for registry authors to know about, and an existing
  Service without it simply shows no login rather than failing loudly.
- Does not cover App config secrets, so the two kinds remain asymmetric.

## Pros and Cons of the Options

### `credentials` on `ServiceSpec` (chosen)

- Good, because it covers Services with and without a browser surface.
- Good, because it names the password option instead of copying the value.
- Good, because the username resolves per instance rather than per catalog entry.
- Bad, because it assumes a single admin identity per Service.
- Bad, because a literal username can drift from the provider unchecked.

### Per-portal credentials

- Good, because the console could render the login beside the portal URL.
- Good, because it reads honestly as "how to log into this surface".
- Bad, because PostgreSQL has no portal, so the case that motivated this ADR
  stays unsolved.

### An `admin-username` config option per Service

- Good, because it needs no schema change and mirrors what Zitadel already does.
- Bad, because for PostgreSQL it is a lie: the superuser name is fixed by the
  image, so an editable option that changes nothing is worse than none.
- Bad, because nothing marks it as *the* admin identity, so the console would be
  back to guessing by name.

### Leave it unmodelled

- Good, because `kubectl` and a direct secrets-provider read already work and are
  gated by cluster access.
- Bad, because Nephos generates a credential and then requires bypassing Nephos
  to use it, which makes turnkey install a trap.

## Links

- Follows [Authenticated Secret Reveal](./20260726-authenticated-secret-reveal.md),
  which supplies the password half.
- Related to [Service Portals](./20260726-service-portals.md) for the surface a
  browser login targets.
- Uses [Catalog Config Schema Exposure](./20260712-catalog-config-schema-exposure.md)
  for how config options reach clients.
