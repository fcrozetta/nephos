# Nephos Doctrine

## Core Identity

Nephos is a platform control plane for composable self-hosted infrastructure.

Nephos is local-first and designed primarily for user-owned infrastructure.

Nephos is not cloud-first, enterprise-first, or SaaS-first.

The architecture may later support lightweight cloud or multi-user scenarios, but that is not the primary design center.

---

## Core Optimization Target

Nephos optimizes for:

- composable infrastructure
- relationship-aware infrastructure
- low operational friction
- local infrastructure ownership
- operational transparency
- capability-based composition
- lifecycle-aware infrastructure management

Nephos does not optimize for:

- exposing raw Kubernetes
- generic container management
- maximizing Kubernetes flexibility
- abstracting infrastructure into opaque magic
- enterprise multi-tenant complexity

---

## Fundamental Product Model

The product model is:

- Apps
- Services
- Capabilities
- Bindings
- Relationships
- Lifecycle state

The product model is NOT:

- containers
- Deployments
- StatefulSets
- Helm charts
- ingress annotations
- raw Kubernetes manifests

Kubernetes resources are implementation details beneath the Nephos platform model.

---

## Core Differentiator

The core differentiator of Nephos is:

capability binding and platform-level relationships.

Nephos is valuable because it understands:

- what Apps require
- what Services provide
- how infrastructure components relate
- how lifecycle affects dependencies
- how infrastructure should be provisioned
- how platform state should evolve over time

Nephos is NOT valuable merely because it deploys workloads.

Deployment alone is commodity functionality.

---

## Apps and Services

Apps and Services are intentionally separate concepts.

Apps are user-facing workloads/products.

Services are shared infrastructure capability providers.

Apps and Services are NOT symmetric.

Apps are expected to be started, stopped, removed, or replaced more frequently.

Services are infrastructure primitives and require dependency-aware lifecycle semantics.

Stopping an App is generally safe.

Stopping a shared Service may affect multiple dependent Apps.

This distinction is foundational.

---

## Services as Capability Providers

Services are not just deployable infrastructure containers.

Services expose capabilities.

Examples:

- PostgreSQL exposes postgres and sql
- Redis exposes redis
- Object Storage exposes s3
- ArangoDB may expose graph-db, document-db, search, and kv
- SMTP exposes smtp

Apps consume capabilities rather than depending directly on infrastructure whenever possible.

This allows future portability and substitution.

The capability layer is one of the most important abstractions in Nephos.

---

## Relationships Are First-Class

Relationships are part of the product model.

Examples:

- App -> Service
- Service -> Capability
- App -> Binding
- App -> Backup policy
- Service -> Dependents

These relationships are not deployment metadata.

They are core platform state.

Nephos should preserve and reason about these relationships.

---

## Nephos and Kubernetes

Kubernetes is the runtime substrate.

Nephos is the platform control plane.

Nephos owns:

- platform intent
- relationships
- capability binding
- lifecycle semantics
- dependency semantics
- provisioning semantics
- ingress intent
- storage intent
- operational visibility

Kubernetes owns:

- runtime execution
- scheduling
- networking primitives
- runtime resources
- probes
- storage primitives

Nephos should use Kubernetes.

Nephos should not compete with Kubernetes.

---

## Kubernetes Complexity Boundary

Users should not need deep Kubernetes knowledge for normal Nephos usage.

Kubernetes concepts leaking directly into product UX is architectural failure.

Bad UX examples:

- ingress annotations
- StatefulSet semantics
- Helm chart internals
- PVC implementation details
- probe configuration
- raw Kubernetes manifests

Good UX examples:

- app visibility
- app lifecycle
- capability binding
- storage intent
- service relationships
- backup policy
- availability intent

The user mental model should be:

- install Apps
- install Services
- bind capabilities
- manage lifecycle
- observe relationships

NOT:

- manage containers and YAML

---

## Runtime Abstraction

Runtime adapters are implementation details.

Users should think in:

- Apps
- Services
- capabilities
- lifecycle
- visibility
- relationships

Users should not need to think in:

- Helm
- StatefulSets
- storage classes
- ingress controllers
- runtime annotations

---

## K3s Philosophy

K3s is the primary runtime backend.

Other Kubernetes-compatible backends may exist later through adapters.

Examples:

- kind
- minikube
- external kubeconfig

These are not equal-priority runtime targets.

K3s is the primary real runtime substrate.

kind and minikube are primarily development/testing/demo adapters unless future needs justify more.

---

## Cluster Adapter Philosophy

Kubernetes compatibility exists mostly above the Kubernetes API boundary.

Cluster lifecycle is backend-specific.

Nephos must isolate backend-specific cluster behavior through cluster adapters.

Examples:

- install
- init
- start
- stop
- destroy
- kubeconfig discovery

Nephos should not pretend all Kubernetes backends behave identically.

---

## Desired State Philosophy

Nephos owns desired platform state.

Lifecycle operations should modify desired state and reconcile into Kubernetes.

Nephos should not become a bag of direct kubectl mutations.

The architectural boundary is:

intent -> desired state -> reconcile into Kubernetes

This is foundational.

---

## Lifecycle Philosophy

stop is not remove.

remove is not destroy.

Stopping should preserve:

- PVCs
- Secrets
- ConfigMaps
- metadata
- bindings
- backup relationships
- service relationships
- platform identity

Lifecycle semantics are platform semantics, not raw runtime operations.

---

## Operational Transparency

Nephos should remain operationally transparent.

Users should be able to understand:

- what exists
- what depends on what
- where data lives
- what Services Apps consume
- what capabilities are bound
- what backups exist
- what lifecycle state exists

Nephos should avoid fake serverless-style opacity.

Infrastructure ownership should remain visible and understandable.

---

## Bootstrap Philosophy

Bootstrap should remain simple and local-first.

Target experience:

- install Nephos
- initialize runtime
- start cluster
- install Services
- install Apps

The user should not need to become a Kubernetes operator to use Nephos.

---

## Catalog Philosophy

The catalog exists to support platform composition.

The catalog is not merely an app marketplace.

Apps and Services exist within a platform relationship model.

The catalog should reinforce composability, lifecycle awareness, and capability binding.

---

## Scope Protection

Nephos should not rebuild Kubernetes subsystems.

Avoid:

- custom scheduler
- custom networking stack
- custom ingress controller
- custom storage engine
- custom orchestrator
- custom container runtime

Kubernetes already solves runtime orchestration.

Nephos should focus on platform semantics and relationships.

---

## External Runtime Platforms

Nephos should not be directly tied to external deployment platforms.

External deployment systems may eventually be supported through optional adapters if useful.

Nephos must preserve ownership of:

- platform semantics
- lifecycle semantics
- capability binding
- provisioning contracts
- relationship modeling

---

## Provisioning Philosophy

Services are not merely deployed resources.

Services implement provisioning contracts.

Examples:

PostgreSQL Service:

- create database
- create user
- grant permissions
- rotate credentials
- backup
- restore

Object Storage Service:

- create bucket/prefix
- create credentials
- apply policies

Provisioning semantics are core platform behavior.

---

## Portability Philosophy

Apps should depend on capabilities rather than concrete infrastructure whenever possible.

Example:

postgres capability could eventually be fulfilled by:

- local PostgreSQL Service
- remote PostgreSQL
- managed provider
- HA cluster
- future alternative implementation

Capability portability is intentional.

---

## Architectural Failure Modes

Nephos is drifting in the wrong direction if it becomes:

- a generic container dashboard
- a raw Kubernetes dashboard
- a thin kubectl wrapper
- an app marketplace without composition
- opaque infrastructure magic
- runtime plumbing without platform semantics

The differentiator must remain:

Apps + Services + capabilities + bindings + platform-level relationships.
