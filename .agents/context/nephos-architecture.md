# Nephos Architecture

## High-Level Architecture

Nephos is a platform control plane over Kubernetes.

Architecture:

Nephos CLI / UI
-> Nephos API
-> Nephos Controller / Reconciler
-> Kubernetes Runtime

Default runtime backend:

- K3s

## Main Components

### CLI

The CLI is the primary early user interface.

It should support:

- nephos cluster *
- nephos app *
- nephos service *

### API

The API should own platform intent.

### Controller / Reconciler

The controller reconciles Nephos desired state into Kubernetes resources.

### Kubernetes Runtime

Kubernetes owns runtime execution.

It owns:

- scheduling
- networking primitives
- Deployments
- StatefulSets
- Services
- Ingress
- PVCs
- Secrets
- ConfigMaps
- Jobs
- CronJobs
- probes

Nephos should use Kubernetes, not reimplement it.

## Catalog Layer

Nephos should have two catalogs:

- App Catalog
- Service Catalog

Apps declare required capabilities.

Services declare exposed capabilities.

Nephos resolves App requirements to installed or installable Services.
