# Source of Truth for Desired State

- Status: draft
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

## Current Leaning

The current leaning is:

- Nephos API/database is canonical
- YAML is import/export
- Kubernetes is runtime state

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

## Proposed Direction

Use Nephos API/database as canonical desired state.

Use YAML as import/export.

Use Kubernetes as runtime state.

Do not implement CRD-first without a later explicit decision.

## Status Notes

This is draft, not accepted.

The architecture should preserve the boundary:

intent -> desired state -> reconcile into Kubernetes
