# Source of Truth for Desired State

- Status: accepted
- Date: 2026-05-17
- Tags: state, api, database, yaml, crd, gitops

## Context and Problem Statement

Nephos needs a canonical source of desired platform state.

Possible sources include:

- Nephos API and database
- YAML files
- Kubernetes CRDs
- GitOps repository

This decision affects the entire architecture.

## Decision

Use the Nephos API and database as the canonical source of desired platform state.

For Phase 1, use SQLite as the canonical desired-state database.

Use YAML for import/export only.

Treat Kubernetes as runtime state, not desired-state authority.

Defer Kubernetes CRDs and GitOps-as-source-of-truth until a later explicit decision.

Use simple explicit SQL migrations for Phase 1 database versioning.

Platform configuration that affects reconciliation, such as ingress root domains, is also desired state in the Nephos API/database.

Do not store ingress root domains only in local startup config or environment variables.

## Considered Options

### Nephos API and Database

Pros:

- clear product ownership
- good fit for UI/API/CLI
- easier lifecycle tracking
- easier relationship modeling
- easier future multi-user support

Cons:

- requires persistence layer
- requires migration/versioning strategy

### YAML Files

Pros:

- simple
- diffable
- easy to export/import

Cons:

- weaker runtime state model
- harder UI-driven mutation
- harder dependency graph management

### Kubernetes CRDs

Pros:

- Kubernetes-native
- strong reconciliation model
- declarative

Cons:

- too heavy too early
- risks turning Nephos into an operator project
- leaks Kubernetes concepts into the product model

### GitOps Repository

Pros:

- auditable
- declarative
- good for advanced users

Cons:

- too high-barrier as default
- not ideal for local-first one-click UX

## Decision Outcome

Chosen option: "Nephos API and Database", because Nephos must own platform intent, relationships, lifecycle semantics, and capability binding above the Kubernetes runtime layer.

The accepted boundary is:

intent -> desired state -> reconcile into Kubernetes

## Status Notes

This decision is accepted.

Do not implement a CRD-first, YAML-first, or GitOps-first source-of-truth model without a later ADR.
