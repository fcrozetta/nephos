# Compose, External Platforms, and Kubernetes Runtime Direction

- Status: accepted
- Date: 2026-05-16
- Tags: runtime, compose, kubernetes, k3s, coolify, platform-direction

## Context and Problem Statement

Nephos started from a simpler container-management direction: multiple Docker Compose stacks, routing, local services, and operational convenience for self-hosted applications.

That model is easy to understand and has a low barrier to entry, but the Nephos redesign shifted toward a stronger platform model.

The emerging Nephos model is not only "run containers". It is:

- Apps
- Services
- capabilities
- bindings
- dependency awareness
- lifecycle semantics
- shared infrastructure
- platform relationships
- operational transparency

This raised the question of whether Docker Compose, Coolify, or Kubernetes should be the foundation.

## Timeline of Considered Directions

### 1. Multiple Docker Compose Stacks

The first model was based around multiple Docker Compose deployments.

This was attractive because it is simple, familiar, local-first, and has a low entry barrier.

It works well for:

- static services
- manual deployments
- direct machine ownership
- simple routing
- simple backups
- low operational overhead

However, Compose becomes weaker once Nephos needs platform behavior.

Compose does not naturally provide a strong model for:

- platform-level desired state
- dependency-aware lifecycle
- shared Services consumed by multiple Apps
- capability binding
- standardized App and Service catalogs
- reconciliation
- health/status aggregation
- namespace/isolation semantics
- future backend abstraction

Compose remains a useful mental baseline, but it is not the preferred runtime substrate for the redesigned Nephos platform.

### 2. Coolify as a Runtime/Deployment Substrate

Coolify was considered because it already provides many practical deployment features:

- application deployment
- Docker Compose deployments
- domains
- SSL
- environment variables
- secrets
- databases
- backups
- UI management
- logs/status
- templates
- multi-server support

Coolify overlaps with many operational features that Nephos would otherwise need to build.

However, Coolify is primarily a deployment platform with its own model.

Nephos is intended to own a higher-level platform model based on:

- Apps
- Services
- capabilities
- bindings
- lifecycle semantics
- shared infrastructure relationships

Using Coolify as the foundational layer would risk constraining Nephos to Coolify's abstractions.

It would also make Nephos dependent on an external deployment platform for its core runtime behavior.

Coolify may still be useful as inspiration or as a possible optional integration later, but Nephos should not depend on it.

### 3. Kubernetes as the Runtime API

Kubernetes was considered because it provides a common runtime API for:

- deployments
- stateful workloads
- services
- ingress
- secrets
- config
- PVCs
- health probes
- jobs
- cron jobs
- scheduling
- reconciliation patterns

Kubernetes aligns better with Nephos once Nephos becomes a platform control plane instead of a container UI.

The important distinction is:

- Kubernetes owns runtime execution.
- Nephos owns platform intent.

Kubernetes should not become the user-facing product model.

Nephos should expose Apps, Services, capabilities, bindings, and lifecycle semantics.

Kubernetes resources are implementation details beneath that model.

### 4. kind and minikube

kind and minikube were considered as possible Kubernetes backends.

They are useful for development, testing, demos, or local experimentation.

They should not be the primary real runtime target for Nephos.

They may be added later through cluster adapters if there is a concrete need.

### 5. K3s

K3s was selected as the default real runtime substrate.

It provides a practical Kubernetes distribution for local/self-hosted infrastructure.

It fits Nephos' local-first direction better than full Kubernetes distributions while preserving the Kubernetes API model.

K3s becomes the primary backend for Nephos.

Other Kubernetes-compatible backends may be added later, but should not be treated as equal priority by default.

## Decision

Nephos will move toward a Kubernetes-based runtime model, with K3s as the default real backend.

Nephos will not depend on Coolify.

Nephos will not remain centered on multiple Docker Compose stacks as the main runtime model.

Nephos will use Kubernetes as the runtime substrate while preserving Nephos as the platform control plane.

## Rationale

The redesigned Nephos model requires platform semantics that Compose does not naturally provide.

Coolify solves many deployment problems, but it would tie Nephos to an external platform and constrain the domain model.

Kubernetes provides the right substrate for runtime primitives, while allowing Nephos to own the higher-level platform model.

K3s provides the most appropriate initial Kubernetes backend for local-first, self-hosted use.

## Consequences

Nephos should implement:

- K3s-first runtime support
- cluster adapter boundaries
- Apps and Services as first-class concepts
- capability binding
- desired-state lifecycle
- dependency-aware Service behavior
- runtime reconciliation into Kubernetes

Nephos should avoid:

- becoming a generic container UI
- exposing Kubernetes directly as the product model
- depending on Coolify
- rebuilding Kubernetes subsystems
- pretending all Kubernetes backends have identical lifecycle behavior

## Final Direction

The final runtime direction is:

- K3s is the primary runtime substrate.
- Kubernetes is the runtime API boundary.
- Nephos is the platform control plane.
- Compose is no longer the primary architecture direction.
- Coolify is not a foundational dependency.
- kind/minikube may be future dev/demo adapters.

The core architectural sentence is:

Nephos owns platform intent; Kubernetes owns runtime execution.
