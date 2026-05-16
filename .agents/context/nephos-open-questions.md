# Nephos Open Questions

## Source of Truth

Question:

What is the canonical source of Nephos desired state?

Candidate options:

- Nephos API plus database
- YAML files
- Kubernetes CRDs
- GitOps repository

Current leaning:

- Nephos API/database should be canonical
- YAML should be import/export
- Kubernetes should be runtime state

Do not implement a CRD-first design without explicit decision.

## App Package Format

Question:

What format defines installable Apps?

Candidates:

- nephos.yml
- Helm chart wrapper
- catalog entry referencing Helm/manifests
- OCI artifact

Need to define schema.

## Namespace Strategy

Question:

What namespace model should Nephos use?

Current leaning:

- one namespace per App
- one namespace per Service
- reserved nephos-system namespace for Nephos control plane
