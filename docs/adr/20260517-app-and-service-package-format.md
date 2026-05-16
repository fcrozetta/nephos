# App and Service Package Format

- Status: draft
- Date: 2026-05-17
- Tags: catalog, manifests, apps, services, schema

## Context and Problem Statement

Nephos needs a format for defining installable Apps and Services.

The format must support catalog entries, runtime deployment, capability requirements, exposed capabilities, provisioning contracts, health checks, and lifecycle behavior.

## Open Questions

What format defines installable Apps?

Candidate options:

- nephos.yml
- Helm chart wrapper
- catalog entry referencing Helm/manifests
- OCI artifact

What format defines installable Services?

A Service package likely needs:

- capabilities exposed
- runtime deployment method
- provisioning contract
- backup/restore contract
- default health checks
- secret outputs
- supported binding types

## Current Leaning

Use a Nephos manifest layer that can reference Helm charts or Kubernetes manifests.

The Nephos manifest should own platform semantics.

Helm or raw manifests should own runtime deployment details.

## Example App Concept

An App declares:

- metadata
- required capabilities
- runtime deployment reference
- ingress needs
- storage needs
- secret/environment mapping

## Example Service Concept

A Service declares:

- metadata
- exposed capabilities
- runtime deployment reference
- provisioning operations
- backup operations
- restore operations
- health checks

## Status Notes

This is draft.

Do not invent package schema silently in implementation without updating this ADR or adding a schema file.
