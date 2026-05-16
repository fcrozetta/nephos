# Secrets Model

- Status: draft
- Date: 2026-05-17
- Tags: secrets, security, kubernetes, bindings

## Context and Problem Statement

Nephos needs a secrets model for credentials created during App-Service binding and Service provisioning.

Initial implementation needs to be simple, but future integrations should remain possible.

## Current Leaning

Use Kubernetes Secrets for the initial implementation.

Support external secret providers later if needed.

Possible future providers:

- Vault
- 1Password
- SOPS
- Infisical
- other external secret managers

## Nephos Responsibilities

Nephos owns the policy of:

- what secrets are created
- where secrets are stored
- how secrets are injected
- how secrets are rotated
- what is preserved on stop/remove/destroy

## Open Questions

Need to define:

- secret naming
- secret ownership labels
- namespace placement
- cross-namespace secret access
- rotation behavior
- preservation on stop
- preservation on remove
- deletion on destroy
- whether secrets are backed up
- redaction in logs/status output

## Status Notes

This is draft.

Do not hardcode secret conventions without documenting them.
