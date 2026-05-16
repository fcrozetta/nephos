# Nephos Command Model

- Status: accepted
- Date: 2026-05-17
- Tags: cli, command-model, lifecycle

## Context and Problem Statement

Nephos needs a command model that reflects the architecture.

There are different operational layers:

- cluster substrate lifecycle
- user-facing App lifecycle
- shared Service lifecycle

Mixing these into one command surface would create ambiguity.

## Decision

Nephos will use separate command groups:

- nephos cluster *
- nephos app *
- nephos service *

`nephos up` and `nephos down` may be shorthand for cluster lifecycle.

They should not directly manage App lifecycle.

## Rationale

Cluster lifecycle is different from platform lifecycle.

Apps and Services run inside Nephos.

The cluster is the runtime substrate underneath Nephos.

## Consequences

Cluster commands manage K3s or future backend adapters.

App commands manage user-facing workloads.

Service commands manage shared platform infrastructure.

Service commands must be dependency-aware.

## Example Commands

Cluster:

- nephos cluster init
- nephos cluster up
- nephos cluster down
- nephos cluster status
- nephos cluster destroy

Apps:

- nephos app install
- nephos app start
- nephos app stop
- nephos app remove
- nephos app destroy

Services:

- nephos service install
- nephos service start
- nephos service stop
- nephos service remove
- nephos service destroy
