# Binding Model

- Status: draft
- Date: 2026-05-17
- Tags: bindings, capabilities, services, apps

## Context and Problem Statement

The binding layer is the heart of Nephos.

Apps consume capabilities exposed by Services.

Nephos needs to define how an App requirement is resolved to a Service and how credentials/configuration are delivered.

## Current Understanding

A binding connects an App requirement to a Service capability.

A binding may include:

- provisioned database
- provisioned user
- bucket or prefix
- credentials
- injected environment variables
- mounted secrets
- connection strings
- network policy
- backup policy references

## Example

An App requires:

- postgres

An installed PostgreSQL Service exposes:

- postgres
- sql

Nephos resolves the requirement, provisions app-scoped database/user credentials, creates Kubernetes Secrets, and injects connection configuration into the App runtime.

## Open Questions

Need to define:

- required vs optional capabilities
- concrete engine preference
- binding names
- secret injection format
- environment variable mapping
- provisioning lifecycle
- rebind behavior
- credential rotation
- whether bindings are immutable after creation
- whether apps can bind to multiple providers of the same capability

## Current Leaning

Apps should depend on capabilities rather than concrete infrastructure whenever possible.

Concrete engine preferences may be allowed where necessary.

## Status Notes

This is draft.

Do not flatten bindings into environment variables only.

Bindings are platform relationships, not just config injection.
