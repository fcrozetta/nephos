# Low-Barrier Local-First Platform

- Status: proposed
- Date: 2026-05-17
- Tags: product, local-first, ux, operations

## Context and Problem Statement

Moving Nephos to Kubernetes/K3s increases operational power but also increases operational complexity.

Nephos should remain approachable for local/self-hosted users.

The user should not need to become a Kubernetes operator just to use Nephos.

## Proposed Decision

Nephos should absorb Kubernetes complexity behind a local-first platform experience.

The target bootstrap should remain simple.

Example target flow:

- brew install nephos
- nephos cluster init
- nephos cluster up
- nephos service install postgres
- nephos app install paperless

## Rationale

Kubernetes provides a strong substrate, but exposing Kubernetes directly would defeat the purpose of Nephos.

Nephos should provide a low-barrier control plane over K3s.

## Consequences

Nephos needs strong defaults.

Nephos needs a clear bootstrap path.

Nephos needs good diagnostics.

Nephos should avoid requiring users to understand Kubernetes internals for normal operations.

## Notes

This ADR is proposed because exact bootstrap/install UX is not fully decided.
