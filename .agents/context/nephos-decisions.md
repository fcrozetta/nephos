# Nephos Decisions

## D001: Nephos is a platform control plane

Nephos is a platform control plane for composable self-hosted infrastructure.

It should not be modeled as a generic container manager.

## D002: K3s is the default runtime backend

K3s is the primary runtime backend.

Other Kubernetes backends may be supported later through cluster adapters.

## D003: Kubernetes is the runtime API boundary

Nephos can be backend-agnostic mostly above the Kubernetes API layer.

Below that layer, cluster lifecycle is backend-specific.

## D004: Apps and Services are top-level concepts

Nephos has two primary installable concepts:

- Apps
- Services

Apps are user-facing workloads.

Services are shared platform infrastructure/capabilities.

## D005: Services expose capabilities

Services expose typed capabilities.

Apps consume capabilities through bindings.

## D006: Nephos API/database is canonical desired state

The Nephos API and database are the source of truth for desired platform state.

SQLite is the Phase 1 database.

YAML is import/export only.

Kubernetes is runtime state.

Kubernetes CRDs and GitOps-as-source-of-truth are deferred.

## D007: Backend and CLI live in separate repositories

The `nephos` repository owns the backend/control plane.

The CLI lives in `../nephos-cli` and `https://github.com/fcrozetta/nephos-cli`.

Do not implement CLI code in this repository without an explicit decision changing that boundary.

## D008: Phase 1 backend stack

The backend stack is Python, FastAPI, SQLite, simple explicit SQL migrations, and the official Python Kubernetes client.

## D009: Phase 1 CLI stack

The CLI stack is Python and Typer, implemented in the separate `nephos-cli` repository.

The CLI talks to the Nephos API/local controller.

The CLI must not become an unstructured direct Kubernetes mutation layer.

## D010: Phase 1 reconciler shape

Use an API-owned in-process reconciler for Phase 1.

Keep module boundaries clear enough to later extract the reconciler into a daemon, worker, scheduled process, or in-cluster controller.

Phase 1 drift handling should detect and report drift and reconcile only Nephos-owned resources when desired state is explicit.
