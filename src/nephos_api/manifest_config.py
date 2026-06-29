import json
from collections.abc import Mapping

from nephos_api.catalog import AppManifest, ServiceManifest


def manifest_config_values(
    row: Mapping[str, object],
    manifest: AppManifest | ServiceManifest,
) -> dict[str, object]:
    values = effective_manifest_config(manifest, {})
    config_json = row.get("config_json")
    if isinstance(config_json, str):
        stored = json.loads(config_json)
        if isinstance(stored, dict):
            values.update(stored)
    return values


def effective_manifest_config(
    manifest: AppManifest | ServiceManifest,
    overrides: Mapping[str, object],
) -> dict[str, object]:
    values: dict[str, object] = {
        option.name: option.default
        for option in manifest.spec.config.options
        if option.default is not None
    }
    values.update(overrides)
    return values
