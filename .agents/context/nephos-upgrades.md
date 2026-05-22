# Nephos Upgrades

## Core Decision

Versions are pinned.

Pinned versions include:

- Apps
- Services
- catalog entries
- Helm charts
- runtime deployment references
- Nephos itself

No automatic `latest` behavior by default.

Upgrades are explicit and manual.

## App Upgrades

Apps should ideally not own durable data directly.

If an App saves durable data, that data should be represented through a Service or resource provider.

App upgrade risk depends on whether the App owns runtime state, uses persistent resources, or requires compatible Service versions.

Detailed App backup-before-upgrade policy is deferred.

## Service Upgrades

Services are higher risk than Apps because they commonly own persistent infrastructure state.

Service upgrades are considered risky by default when persistent data exists.

Risky Service upgrades should require backup/checkpoint confirmation once the Service declares backup support.

Until backup support exists for a Service, Nephos must warn that no supported backup exists.

## Rollback

Rollback is best-effort in Phase 1.

Rollback is not guaranteed.

Nephos should not imply that downgrading a chart, App, or Service restores data compatibility.

## Compatibility

Compatibility checks are reserved for later design.

Phase 1 should track installed and desired versions, but deep compatibility validation is deferred.

## Guardrails

Do not silently upgrade Apps, Services, charts, or catalogs.

Do not use automatic latest by default.

Do not present Service upgrades as safe when backup support is missing.
