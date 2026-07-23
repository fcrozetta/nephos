"""Preflight dependency planning for lazy provider install (#79).

Given an App catalog entry and the currently-installed Service instances, work
out, per capability requirement, whether it is already satisfied, needs a pick
among installed providers, can be satisfied by installing a catalog provider, or
cannot be satisfied at all. This is read-only: it resolves and reports, it never
installs anything. The commit path (installing the chosen providers, then the
app) is separate.

State per requirement:
- satisfied:      exactly one eligible installed provider (auto-binds).
- needs_selection: more than one eligible installed provider (user picks one).
- installable:    no installed provider, but >= 1 catalog provider could be
                  installed (candidates in core -> mythos -> community order).
- unresolvable:   no installed provider and no catalog provider.
"""

from __future__ import annotations

from typing import Any

from nephos_api.catalog import (
    CatalogEntryNotFoundError,
    CatalogLoader,
    CatalogSourceNotFoundError,
    entry_provides,
)


def build_app_dependency_plan(
    *,
    app_entry: dict[str, Any],
    service_rows: list[dict[str, object]],
    loader: CatalogLoader,
) -> dict[str, Any]:
    requirements = [
        _plan_requirement(requirement, service_rows, loader)
        for requirement in app_entry["requires"]
    ]
    return {
        "app": {"name": app_entry["name"], "source": app_entry["source"]},
        "requirements": requirements,
        # Every requirement can be met (already, by selection, or by installing a
        # provider). A single unresolvable requirement makes the app un-installable.
        "satisfiable": all(
            item["state"] != "unresolvable" for item in requirements
        ),
    }


def _plan_requirement(
    requirement: dict[str, Any],
    service_rows: list[dict[str, object]],
    loader: CatalogLoader,
) -> dict[str, Any]:
    capability = requirement["capability"]
    protocol = requirement.get("protocol")
    provider_pin = requirement.get("provider")

    installed = _eligible_installed_providers(
        service_rows, loader, capability, protocol, provider_pin
    )
    item: dict[str, Any] = {
        "alias": requirement["alias"],
        "capability": capability,
        "installedProviders": installed,
        "candidates": [],
    }
    if protocol is not None:
        item["protocol"] = protocol

    if len(installed) == 1:
        item["state"] = "satisfied"
        return item
    if len(installed) > 1:
        item["state"] = "needs_selection"
        return item

    candidates = _catalog_candidates(loader, capability, protocol, provider_pin)
    item["candidates"] = candidates
    item["state"] = "installable" if candidates else "unresolvable"
    return item


def _eligible_installed_providers(
    service_rows: list[dict[str, object]],
    loader: CatalogLoader,
    capability: str,
    protocol: str | None,
    provider_pin: str | None,
) -> list[str]:
    """Slugs of running Service instances that provide the capability.

    Mirrors the install path's provider eligibility: capability/protocol match
    on the instance's catalog entry, plus available (running, not delete-
    requested). Honors an optional requirement.provider pin (catalog name).
    """
    slugs: list[str] = []
    for row in service_rows:
        if not _row_is_available(row):
            continue
        if provider_pin is not None and str(row["catalog_name"]) != provider_pin:
            continue
        entry = _service_entry_or_none(loader, row)
        if entry is None:
            continue
        if entry_provides(entry, capability, protocol):
            slugs.append(str(row["slug"]))
    return slugs


def _catalog_candidates(
    loader: CatalogLoader,
    capability: str,
    protocol: str | None,
    provider_pin: str | None,
) -> list[dict[str, str]]:
    entries = loader.list_service_providers(capability, protocol)
    if provider_pin is not None:
        entries = [entry for entry in entries if entry["name"] == provider_pin]
    # list_service_providers already yields registry precedence order.
    return [{"name": entry["name"], "source": entry["source"]} for entry in entries]


def _row_is_available(row: dict[str, object]) -> bool:
    # Same rule as the install path's _binding_provider_is_available.
    return row["delete_requested_at"] is None and row["lifecycle"] == "running"


def _service_entry_or_none(
    loader: CatalogLoader, row: dict[str, object]
) -> dict[str, Any] | None:
    try:
        return loader.get_service(
            str(row["catalog_name"]), source=str(row["catalog_source_id"])
        )
    except (CatalogEntryNotFoundError, CatalogSourceNotFoundError):
        # An installed instance whose catalog entry is gone can't be matched;
        # treat it as not-a-provider rather than failing the whole plan.
        return None
