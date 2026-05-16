# Controller and Reconciliation Architecture

- Status: draft
- Date: 2026-05-17
- Tags: controller, reconciliation, cli, api, architecture

## Context and Problem Statement

Nephos needs to reconcile desired platform state into Kubernetes.

The exact implementation shape is not yet decided.

Possible models include:

- CLI-driven local reconciliation
- API-driven reconciliation
- controller running inside the cluster
- hybrid approach

## Current Leaning

Start simple, but preserve the architecture boundary:

intent -> desired state -> reconcile into Kubernetes

Avoid turning the CLI into a bag of direct Kubernetes mutations.

## Considered Options

### CLI-driven local reconciliation

Pros:

- simpler initially
- lower infrastructure overhead
- easier early development

Cons:

- weaker continuous reconciliation
- harder UI/API integration later
- less platform-like

### API-driven reconciliation

Pros:

- cleaner product architecture
- supports CLI and UI
- centralizes platform state

Cons:

- requires API and persistence earlier

### In-cluster controller

Pros:

- Kubernetes-native
- continuous reconciliation
- strong runtime ownership

Cons:

- heavier early implementation
- risks CRD/operator complexity too soon

## Status Notes

This is draft.

Implementation can start pragmatic, but must not violate the conceptual boundary.
