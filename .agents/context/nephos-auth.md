# Nephos Auth

## Phase 1 Decision

Nephos Phase 1 is single-owner and local-first.

The CLI is a trusted local client.

No login is required in Phase 1.

No multi-user model is required in Phase 1.

No roles or RBAC are required in Phase 1.

The Web UI is deferred for Phase 1.

Zitadel is an alpha backbone Service, not Nephos control-plane login.

Zitadel provides identity capabilities to Apps through protocol-aware bindings:

- `oidc/oidc`
- `service-account/jwt`

Zitadel login/admin UI are Service surfaces/routes. They are not a separate App.

Adding Zitadel to the alpha backbone does not change the Phase 1 Nephos API/CLI
auth model: the CLI remains a trusted local client, and Nephos itself still has
no Phase 1 login/RBAC requirement.

## Future Direction

When the Web UI is introduced, it should require local-owner auth.

Enterprise RBAC is not the default Web UI target.

Friend, cloud, hosted, and multi-user scenarios are out of scope for Phase 1 but not forbidden forever.

## API Exposure Guardrail

Trusted local CLI does not mean the API should be exposed unauthenticated on an untrusted network.

If Nephos supports non-local API exposure, auth must be revisited before that behavior is supported.

## Non-Goals

Phase 1 does not include:

- user accounts
- organizations
- teams
- invitations
- roles
- RBAC
- SSO
- enterprise IAM
- hosted/SaaS identity

These non-goals describe Nephos control-plane auth. They do not forbid a Zitadel
Service from provisioning app-facing OIDC clients or service-account material.
