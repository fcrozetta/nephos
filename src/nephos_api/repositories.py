from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from nephos_api.config import Settings
from nephos_api.db import connect, transaction
from nephos_api.domain import (
    new_id,
    utc_now,
    validate_machine_identifier,
    validate_root_domain,
)
from nephos_api.errors import NephosError


def _json(data: dict[str, Any] | list[Any] | None) -> str:
    return json.dumps(data if data is not None else {}, sort_keys=True, separators=(",", ":"))


def _decode_json(raw: str | None) -> Any:
    if raw is None:
        return None
    return json.loads(raw)


def _domain_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "domain": row["domain"],
        "default": bool(row["is_default"]),
        "generation": row["generation"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def _status_from_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "resourceType": row["resource_type"],
        "resourceId": row["resource_id"],
        "level": row["level"],
        "lifecycle": row["lifecycle"],
        "reconciliation": row["reconciliation"],
        "reason": row["reason"],
        "message": row["message"],
        "evidence": _decode_json(row["evidence_json"]),
        "observedGeneration": row["observed_generation"],
        "observedAt": row["observed_at"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def _service_from_row(
    row: sqlite3.Row,
    *,
    provides: list[dict[str, Any]] | None = None,
    dependents: list[dict[str, Any]] | None = None,
    status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    catalog_ref: dict[str, Any] = {
        "kind": row["catalog_kind"],
        "name": row["catalog_name"],
        "source": row["catalog_source_id"],
        "manifestDigest": row["manifest_digest"],
    }
    if row["catalog_version"]:
        catalog_ref["version"] = row["catalog_version"]
    snapshot = {
        "id": row["id"],
        "slug": row["slug"],
        "kind": "Service",
        "lifecycle": row["lifecycle"],
        "generation": row["generation"],
        "catalogRef": catalog_ref,
        "config": _decode_json(row["config_json"]),
        "provides": provides or [],
        "dependents": dependents or [],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }
    if status is not None:
        snapshot["status"] = status
    return snapshot


def _app_from_row(
    row: sqlite3.Row,
    *,
    bindings: list[dict[str, Any]] | None = None,
    routes: list[dict[str, Any]] | None = None,
    status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    catalog_ref: dict[str, Any] = {
        "kind": row["catalog_kind"],
        "name": row["catalog_name"],
        "source": row["catalog_source_id"],
        "manifestDigest": row["manifest_digest"],
    }
    if row["catalog_version"]:
        catalog_ref["version"] = row["catalog_version"]
    snapshot = {
        "id": row["id"],
        "slug": row["slug"],
        "kind": "App",
        "lifecycle": row["lifecycle"],
        "generation": row["generation"],
        "catalogRef": catalog_ref,
        "config": _decode_json(row["config_json"]),
        "bindings": bindings or [],
        "routes": routes or [],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }
    if status is not None:
        snapshot["status"] = status
    return snapshot


def _compact_status_from_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "level": row["level"],
        "reason": row["reason"],
        "message": row["message"],
        "observedAt": row["observed_at"],
    }


def _binding_from_row(row: sqlite3.Row, status: dict[str, Any] | None = None) -> dict[str, Any]:
    snapshot = {
        "id": row["id"],
        "alias": row["alias"],
        "capability": row["capability"],
        "appInstance": row["app_slug"],
        "serviceInstance": row["service_slug"],
        "output": _decode_json(row["output_summary_json"]),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }
    if status is not None:
        snapshot["status"] = status
    return snapshot


def _app_binding_entry_from_row(
    row: sqlite3.Row,
    status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": row["id"],
        "alias": row["alias"],
        "capability": row["capability"],
        "serviceInstance": row["service_slug"],
        "status": status,
    }


def _route_entry(route: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": route["name"],
        "visibility": route["visibility"],
        "target": route["target"],
        "canonicalUrl": None,
        "aliases": [],
        "status": None,
    }


def _service_provides_from_catalog(settings: Settings, row: sqlite3.Row) -> list[dict[str, Any]]:
    from nephos_api.catalog import CatalogLoader

    try:
        summary = CatalogLoader(settings).get_entry(
            "Service",
            row["catalog_name"],
            source_id=row["catalog_source_id"],
        )
    except NephosError:
        return []
    return summary.get("provides", [])


def _app_routes_from_catalog(settings: Settings, row: sqlite3.Row) -> list[dict[str, Any]]:
    from nephos_api.catalog import CatalogLoader

    try:
        summary = CatalogLoader(settings).get_entry(
            "App",
            row["catalog_name"],
            source_id=row["catalog_source_id"],
        )
    except NephosError:
        return []
    return [_route_entry(route) for route in summary.get("routes", [])]


def _binding_output_summary(
    *,
    app_slug: str,
    alias: str,
    capability: str,
    output_targets: list[str],
) -> dict[str, Any]:
    if "app-secret" not in output_targets:
        return {}
    return {
        "target": "app-secret",
        "secretName": f"nephos-bind-{alias}",
        "namespace": f"app-{app_slug}",
        "keys": _secret_keys_for_capability(capability),
        "redacted": True,
    }


def _secret_keys_for_capability(capability: str) -> list[str]:
    if capability == "postgres":
        return ["host", "port", "database", "username", "password", "uri"]
    return []


def _reconciliation_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "targetType": row["target_type"],
        "targetId": row["target_id"],
        "targetGeneration": row["target_generation"],
        "action": row["action"],
        "state": row["state"],
        "error": row["error"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def _reconciliation_request_from_row(row: sqlite3.Row) -> dict[str, Any]:
    request = _reconciliation_from_row(row)
    request["payload"] = _decode_json(row["payload_json"]) or {}
    request["targetSnapshot"] = _decode_json(row["target_snapshot_json"]) or {}
    return request


def _status_snapshot(
    *,
    resource_type: str,
    resource_id: str,
    level: str = "pending",
    lifecycle: str = "not_applicable",
    reconciliation: str = "pending",
    reason: str,
    message: str,
    observed_generation: int | None,
    evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    now = utc_now()
    return {
        "id": new_id("status_snapshot"),
        "resourceType": resource_type,
        "resourceId": resource_id,
        "level": level,
        "lifecycle": lifecycle,
        "reconciliation": reconciliation,
        "reason": reason,
        "message": message,
        "evidence": evidence or [],
        "observedGeneration": observed_generation,
        "observedAt": now,
        "createdAt": now,
        "updatedAt": now,
    }


def _insert_reconciliation_request(
    connection: sqlite3.Connection,
    *,
    target_type: str,
    target_id: str,
    target_generation: int | None,
    action: str,
    payload: dict[str, Any] | None = None,
    target_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = utc_now()
    request_id = new_id("reconciliation_request")
    connection.execute(
        """
        INSERT INTO reconciliation_requests(
            id,
            target_type,
            target_id,
            target_generation,
            action,
            payload_json,
            target_snapshot_json,
            state,
            error,
            created_at,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', NULL, ?, ?)
        """,
        (
            request_id,
            target_type,
            target_id,
            target_generation,
            action,
            _json(payload),
            _json(target_snapshot),
            now,
            now,
        ),
    )
    row = connection.execute(
        "SELECT * FROM reconciliation_requests WHERE id = ?",
        (request_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError("failed to read created reconciliation request")
    return _reconciliation_from_row(row)


def _upsert_status_snapshot(
    connection: sqlite3.Connection,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    connection.execute(
        """
        INSERT INTO status_snapshots(
            id,
            resource_type,
            resource_id,
            level,
            lifecycle,
            reconciliation,
            reason,
            message,
            evidence_json,
            observed_generation,
            observed_at,
            created_at,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(resource_type, resource_id) DO UPDATE SET
            level = excluded.level,
            lifecycle = excluded.lifecycle,
            reconciliation = excluded.reconciliation,
            reason = excluded.reason,
            message = excluded.message,
            evidence_json = excluded.evidence_json,
            observed_generation = excluded.observed_generation,
            observed_at = excluded.observed_at,
            updated_at = excluded.updated_at
        """,
        (
            snapshot["id"],
            snapshot["resourceType"],
            snapshot["resourceId"],
            snapshot["level"],
            snapshot["lifecycle"],
            snapshot["reconciliation"],
            snapshot["reason"],
            snapshot["message"],
            _json(snapshot["evidence"]),
            snapshot["observedGeneration"],
            snapshot["observedAt"],
            snapshot["createdAt"],
            snapshot["updatedAt"],
        ),
    )
    return snapshot


def _validate_destroy_confirmation(*, slug: str, confirm: str | None) -> None:
    expected = f"destroy {slug}"
    if confirm != expected:
        raise NephosError(
            "destroy_confirmation_required",
            "Destroy requires explicit confirmation.",
            status_code=422,
            details={"expected": expected, "received": confirm},
        )


def _lifecycle_status_message(kind: str, action: str) -> str:
    if action == "reconcile":
        return f"Manual {kind} reconciliation was requested."
    if action == "destroy":
        return f"{kind} destroy was requested and awaits reconciliation before state deletion."
    return f"{kind} lifecycle action '{action}' was recorded and awaits reconciliation."


class ReconciliationRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def db_path(self) -> Path:
        return self.settings.db_path

    def claim_next_pending(self) -> dict[str, Any] | None:
        """Claim the oldest pending request for the single serialized worker."""
        now = utc_now()
        with connect(self.db_path) as connection, transaction(connection):
            row = connection.execute(
                """
                SELECT * FROM reconciliation_requests
                WHERE state = 'pending'
                ORDER BY created_at ASC, id ASC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                """
                UPDATE reconciliation_requests
                SET state = 'running',
                    error = NULL,
                    updated_at = ?
                WHERE id = ? AND state = 'pending'
                """,
                (now, row["id"]),
            )
            updated = connection.execute(
                "SELECT * FROM reconciliation_requests WHERE id = ?",
                (row["id"],),
            ).fetchone()
            if updated is None:
                raise RuntimeError("failed to read claimed reconciliation request")
            return _reconciliation_request_from_row(updated)

    def finish_request(
        self,
        *,
        request_id: str,
        state: str,
        error: str | None = None,
        status: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        with connect(self.db_path) as connection, transaction(connection):
            if status is not None:
                _upsert_status_snapshot(connection, status)
            connection.execute(
                """
                UPDATE reconciliation_requests
                SET state = ?,
                    error = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (state, error, now, request_id),
            )
            row = connection.execute(
                "SELECT * FROM reconciliation_requests WHERE id = ?",
                (request_id,),
            ).fetchone()
            if row is None:
                raise RuntimeError("failed to read finished reconciliation request")
            return _reconciliation_request_from_row(row)

    def get_request(self, *, request_id: str) -> dict[str, Any]:
        with connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT * FROM reconciliation_requests WHERE id = ?",
                (request_id,),
            ).fetchone()
            if row is None:
                raise NephosError(
                    "reconciliation_request_not_found",
                    "Reconciliation request not found.",
                    status_code=404,
                    details={"reconciliationRequest": request_id},
                )
            return _reconciliation_request_from_row(row)

    def get_status(self, *, resource_type: str, resource_id: str) -> dict[str, Any] | None:
        with connect(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT * FROM status_snapshots
                WHERE resource_type = ? AND resource_id = ?
                """,
                (resource_type, resource_id),
            ).fetchone()
            return _status_from_row(row)


class AppInstanceRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def db_path(self) -> Path:
        return self.settings.db_path

    def list_apps(self) -> list[dict[str, Any]]:
        with connect(self.db_path) as connection:
            rows = connection.execute("SELECT * FROM app_instances ORDER BY slug ASC").fetchall()
            return [self._app_snapshot(connection, row) for row in rows]

    def get_app(self, *, slug: str) -> dict[str, Any]:
        slug = validate_machine_identifier(slug, field="appInstance")
        with connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT * FROM app_instances WHERE slug = ?",
                (slug,),
            ).fetchone()
            if row is None:
                raise NephosError(
                    "app_instance_not_found",
                    "App instance not found.",
                    status_code=404,
                    details={"appInstance": slug},
                )
            return self._app_snapshot(connection, row)

    def install_app(
        self,
        *,
        catalog_ref: dict[str, Any],
        instance_name: str | None,
        config: dict[str, Any],
        bindings: dict[str, Any],
    ) -> dict[str, Any]:
        from nephos_api.catalog import AppManifest, CatalogLoader

        if bindings:
            raise NephosError(
                "explicit_binding_selection_unsupported",
                "Explicit App binding selection is reserved and not implemented yet.",
                status_code=422,
                details={"bindings": bindings},
            )
        if catalog_ref.get("kind") != "App":
            raise NephosError(
                "invalid_catalog_ref",
                "App install requires catalogRef.kind to be App.",
                status_code=422,
                details={"catalogRef": catalog_ref},
            )
        catalog_name = catalog_ref.get("name")
        if not isinstance(catalog_name, str):
            raise NephosError(
                "invalid_catalog_ref",
                "App install requires catalogRef.name.",
                status_code=422,
                details={"catalogRef": catalog_ref},
            )

        loader = CatalogLoader(self.settings)
        entry = loader.resolve_entry("App", catalog_name, source_id=catalog_ref.get("source"))
        if not isinstance(entry.manifest, AppManifest):
            raise RuntimeError("resolved non-App manifest for App install")
        slug = validate_machine_identifier(instance_name or entry.name, field="instanceName")
        app_id = new_id("app_instance")
        now = utc_now()
        catalog_summary = loader.get_entry("App", entry.name, source_id=entry.source.id)
        requirements = catalog_summary.get("requires", [])
        routes = [_route_entry(route) for route in catalog_summary.get("routes", [])]

        with connect(self.db_path) as connection, transaction(connection):
            binding_resolutions = self._resolve_binding_requirements(
                connection,
                requirements=requirements,
                app_slug=slug,
            )
            try:
                connection.execute(
                    """
                    INSERT INTO app_instances(
                        id,
                        slug,
                        catalog_kind,
                        catalog_name,
                        catalog_version,
                        catalog_source_id,
                        catalog_source_path,
                        manifest_digest,
                        lifecycle,
                        generation,
                        config_json,
                        delete_requested_at,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'running', 1, ?, NULL, ?, ?)
                    """,
                    (
                        app_id,
                        slug,
                        "App",
                        entry.name,
                        entry.manifest.metadata.version,
                        entry.source.id,
                        str(entry.manifest_path),
                        entry.manifest_digest,
                        _json(config),
                        now,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise NephosError(
                    "app_instance_conflict",
                    "App instance name already exists.",
                    status_code=409,
                    details={"appInstance": slug},
                ) from exc

            for resolution in binding_resolutions:
                connection.execute(
                    """
                    INSERT INTO bindings(
                        id,
                        app_instance_id,
                        service_instance_id,
                        alias,
                        capability,
                        generation,
                        output_summary_json,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)
                    """,
                    (
                        new_id("binding"),
                        app_id,
                        resolution["serviceId"],
                        resolution["alias"],
                        resolution["capability"],
                        _json(resolution["outputSummary"]),
                        now,
                        now,
                    ),
                )

            row = connection.execute(
                "SELECT * FROM app_instances WHERE id = ?",
                (app_id,),
            ).fetchone()
            resource = self._app_snapshot(connection, row, routes=routes)
            reconciliation = _insert_reconciliation_request(
                connection,
                target_type="app_instance",
                target_id=app_id,
                target_generation=resource["generation"],
                action="app.install",
                payload={"catalogRef": catalog_ref, "instanceName": slug},
                target_snapshot=resource,
            )
            status = _upsert_status_snapshot(
                connection,
                _status_snapshot(
                    resource_type="app_instance",
                    resource_id=app_id,
                    lifecycle="running",
                    reason="reconciliation_pending",
                    message="App desired state and bindings were created and await reconciliation.",
                    observed_generation=resource["generation"],
                ),
            )
            resource["status"] = status
        return {"resource": resource, "reconciliation": reconciliation, "status": status}

    def lifecycle_action(
        self,
        *,
        slug: str,
        action: str,
        confirm: str | None = None,
    ) -> dict[str, Any]:
        if action not in {"start", "stop", "remove", "destroy"}:
            raise NephosError(
                "unsupported_lifecycle_action",
                "Unsupported App lifecycle action.",
                status_code=404,
                details={"appInstance": slug, "action": action},
            )
        slug = validate_machine_identifier(slug, field="appInstance")
        if action == "destroy":
            _validate_destroy_confirmation(slug=slug, confirm=confirm)

        now = utc_now()
        with connect(self.db_path) as connection, transaction(connection):
            row = self._app_row_for_update(connection, slug)
            if action == "destroy":
                should_increment = row["delete_requested_at"] is None
                if should_increment:
                    connection.execute(
                        """
                        UPDATE app_instances
                        SET delete_requested_at = ?,
                            generation = generation + 1,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (now, now, row["id"]),
                    )
            else:
                lifecycle = {"start": "running", "stop": "stopped", "remove": "removed"}[action]
                if row["lifecycle"] != lifecycle or row["delete_requested_at"] is not None:
                    connection.execute(
                        """
                        UPDATE app_instances
                        SET lifecycle = ?,
                            delete_requested_at = NULL,
                            generation = generation + 1,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (lifecycle, now, row["id"]),
                    )

            updated = connection.execute(
                "SELECT * FROM app_instances WHERE slug = ?",
                (slug,),
            ).fetchone()
            resource = self._app_snapshot(connection, updated)
            payload: dict[str, Any] = {"action": action}
            if action == "destroy":
                payload["confirm"] = confirm
            reconciliation = _insert_reconciliation_request(
                connection,
                target_type="app_instance",
                target_id=resource["id"],
                target_generation=resource["generation"],
                action=f"app.{action}",
                payload=payload,
                target_snapshot=resource,
            )
            status = _upsert_status_snapshot(
                connection,
                _status_snapshot(
                    resource_type="app_instance",
                    resource_id=resource["id"],
                    lifecycle=resource["lifecycle"],
                    reason="reconciliation_pending",
                    message=_lifecycle_status_message("App", action),
                    observed_generation=resource["generation"],
                ),
            )
            resource["status"] = status
        return {"resource": resource, "reconciliation": reconciliation, "status": status}

    def reconcile(self, *, slug: str) -> dict[str, Any]:
        slug = validate_machine_identifier(slug, field="appInstance")
        with connect(self.db_path) as connection, transaction(connection):
            row = self._app_row_for_update(connection, slug)
            resource = self._app_snapshot(connection, row)
            reconciliation = _insert_reconciliation_request(
                connection,
                target_type="app_instance",
                target_id=resource["id"],
                target_generation=resource["generation"],
                action="app.reconcile",
                payload={"manual": True},
                target_snapshot=resource,
            )
            status = _upsert_status_snapshot(
                connection,
                _status_snapshot(
                    resource_type="app_instance",
                    resource_id=resource["id"],
                    lifecycle=resource["lifecycle"],
                    reason="manual_reconciliation_requested",
                    message=_lifecycle_status_message("App", "reconcile"),
                    observed_generation=resource["generation"],
                ),
            )
            resource["status"] = status
        return {"resource": resource, "reconciliation": reconciliation, "status": status}

    def _app_row_for_update(self, connection: sqlite3.Connection, slug: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM app_instances WHERE slug = ?",
            (slug,),
        ).fetchone()
        if row is None:
            raise NephosError(
                "app_instance_not_found",
                "App instance not found.",
                status_code=404,
                details={"appInstance": slug},
            )
        return row

    def _app_snapshot(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        *,
        routes: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        status_row = connection.execute(
            """
            SELECT * FROM status_snapshots
            WHERE resource_type = 'app_instance' AND resource_id = ?
            """,
            (row["id"],),
        ).fetchone()
        return _app_from_row(
            row,
            bindings=self._bindings_for_app(connection, row["id"]),
            routes=routes if routes is not None else _app_routes_from_catalog(self.settings, row),
            status=_status_from_row(status_row),
        )

    def _bindings_for_app(
        self,
        connection: sqlite3.Connection,
        app_id: str,
    ) -> list[dict[str, Any]]:
        rows = connection.execute(
            """
            SELECT
                b.*,
                a.slug AS app_slug,
                s.slug AS service_slug
            FROM bindings b
            JOIN app_instances a ON a.id = b.app_instance_id
            JOIN service_instances s ON s.id = b.service_instance_id
            WHERE b.app_instance_id = ?
            ORDER BY b.alias ASC
            """,
            (app_id,),
        ).fetchall()
        entries: list[dict[str, Any]] = []
        for row in rows:
            status_row = connection.execute(
                """
                SELECT * FROM status_snapshots
                WHERE resource_type = 'binding' AND resource_id = ?
                """,
                (row["id"],),
            ).fetchone()
            entries.append(_app_binding_entry_from_row(row, _compact_status_from_row(status_row)))
        return entries

    def _resolve_binding_requirements(
        self,
        connection: sqlite3.Connection,
        *,
        requirements: list[dict[str, Any]],
        app_slug: str,
    ) -> list[dict[str, Any]]:
        resolutions: list[dict[str, Any]] = []
        missing: list[dict[str, Any]] = []
        ambiguous: list[dict[str, Any]] = []
        for requirement in requirements:
            capability = requirement["capability"]
            alias = validate_machine_identifier(requirement["alias"], field="binding alias")
            provider = requirement.get("provider")
            candidates = self._candidate_services(
                connection,
                capability=capability,
                provider=provider,
            )
            requirement_details = {
                "alias": alias,
                "capability": capability,
                **({"provider": provider} if provider else {}),
            }
            if not candidates:
                missing.append(requirement_details)
                continue
            if len(candidates) > 1:
                ambiguous.append(
                    {
                        **requirement_details,
                        "candidates": [candidate["details"] for candidate in candidates],
                    }
                )
                continue
            candidate = candidates[0]
            provide = candidate["provide"]
            resolutions.append(
                {
                    "alias": alias,
                    "capability": capability,
                    "serviceId": candidate["id"],
                    "serviceInstance": candidate["slug"],
                    "outputSummary": _binding_output_summary(
                        app_slug=app_slug,
                        alias=alias,
                        capability=capability,
                        output_targets=provide.get("bindingOutputTargets", []),
                    ),
                }
            )
        if missing:
            raise NephosError(
                "app_binding_provider_not_found",
                "App install requires an installed Service provider for every required capability.",
                status_code=422,
                details={"requirements": missing},
            )
        if ambiguous:
            raise NephosError(
                "app_binding_provider_ambiguous",
                (
                    "Multiple installed Service providers match an App requirement; "
                    "explicit binding selection is required."
                ),
                status_code=409,
                details={"requirements": ambiguous},
            )
        return resolutions

    def _candidate_services(
        self,
        connection: sqlite3.Connection,
        *,
        capability: str,
        provider: str | None,
    ) -> list[dict[str, Any]]:
        rows = connection.execute(
            """
            SELECT * FROM service_instances
            WHERE lifecycle != 'removed'
            ORDER BY slug ASC
            """
        ).fetchall()
        candidates: list[dict[str, Any]] = []
        for row in rows:
            if provider and provider not in {row["slug"], row["catalog_name"]}:
                continue
            matching_provides = [
                provide
                for provide in _service_provides_from_catalog(self.settings, row)
                if provide["capability"] == capability
            ]
            if not matching_provides:
                continue
            provide = matching_provides[0]
            candidates.append(
                {
                    "id": row["id"],
                    "slug": row["slug"],
                    "provide": provide,
                    "details": {
                        "serviceInstance": row["slug"],
                        "catalogRef": {
                            "kind": row["catalog_kind"],
                            "name": row["catalog_name"],
                            "source": row["catalog_source_id"],
                            "manifestDigest": row["manifest_digest"],
                        },
                        "provides": matching_provides,
                    },
                }
            )
        return candidates


class ServiceInstanceRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def db_path(self) -> Path:
        return self.settings.db_path

    def list_services(self) -> list[dict[str, Any]]:
        with connect(self.db_path) as connection:
            rows = connection.execute(
                "SELECT * FROM service_instances ORDER BY slug ASC"
            ).fetchall()
            return [self._service_snapshot(connection, row) for row in rows]

    def get_service(self, *, slug: str) -> dict[str, Any]:
        slug = validate_machine_identifier(slug, field="serviceInstance")
        with connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT * FROM service_instances WHERE slug = ?",
                (slug,),
            ).fetchone()
            if row is None:
                raise NephosError(
                    "service_instance_not_found",
                    "Service instance not found.",
                    status_code=404,
                    details={"serviceInstance": slug},
                )
            return self._service_snapshot(connection, row)

    def install_service(
        self,
        *,
        catalog_ref: dict[str, Any],
        instance_name: str | None,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        from nephos_api.catalog import CatalogLoader, ServiceManifest

        if catalog_ref.get("kind") != "Service":
            raise NephosError(
                "invalid_catalog_ref",
                "Service install requires catalogRef.kind to be Service.",
                status_code=422,
                details={"catalogRef": catalog_ref},
            )
        catalog_name = catalog_ref.get("name")
        if not isinstance(catalog_name, str):
            raise NephosError(
                "invalid_catalog_ref",
                "Service install requires catalogRef.name.",
                status_code=422,
                details={"catalogRef": catalog_ref},
            )

        entry = CatalogLoader(self.settings).resolve_entry(
            "Service",
            catalog_name,
            source_id=catalog_ref.get("source"),
        )
        if not isinstance(entry.manifest, ServiceManifest):
            raise RuntimeError("resolved non-Service manifest for Service install")
        slug = validate_machine_identifier(
            instance_name or entry.name,
            field="instanceName",
        )
        service_id = new_id("service_instance")
        now = utc_now()

        with connect(self.db_path) as connection, transaction(connection):
            try:
                connection.execute(
                    """
                    INSERT INTO service_instances(
                        id,
                        slug,
                        catalog_kind,
                        catalog_name,
                        catalog_version,
                        catalog_source_id,
                        catalog_source_path,
                        manifest_digest,
                        lifecycle,
                        generation,
                        config_json,
                        delete_requested_at,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'running', 1, ?, NULL, ?, ?)
                    """,
                    (
                        service_id,
                        slug,
                        "Service",
                        entry.name,
                        entry.manifest.metadata.version,
                        entry.source.id,
                        str(entry.manifest_path),
                        entry.manifest_digest,
                        _json(config),
                        now,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise NephosError(
                    "service_instance_conflict",
                    "Service instance name already exists.",
                    status_code=409,
                    details={"serviceInstance": slug},
                ) from exc

            row = connection.execute(
                "SELECT * FROM service_instances WHERE id = ?",
                (service_id,),
            ).fetchone()
            catalog_summary = CatalogLoader(self.settings).get_entry(
                "Service",
                entry.name,
                source_id=entry.source.id,
            )
            resource = self._service_snapshot(
                connection,
                row,
                provides=catalog_summary.get("provides", []),
            )
            reconciliation = _insert_reconciliation_request(
                connection,
                target_type="service_instance",
                target_id=service_id,
                target_generation=resource["generation"],
                action="service.install",
                payload={"catalogRef": catalog_ref, "instanceName": slug},
                target_snapshot=resource,
            )
            status = _upsert_status_snapshot(
                connection,
                _status_snapshot(
                    resource_type="service_instance",
                    resource_id=service_id,
                    lifecycle="running",
                    reason="reconciliation_pending",
                    message="Service desired state was created and awaits reconciliation.",
                    observed_generation=resource["generation"],
                ),
            )
            resource["status"] = status
        return {"resource": resource, "reconciliation": reconciliation, "status": status}

    def lifecycle_action(
        self,
        *,
        slug: str,
        action: str,
        force: bool = False,
        confirm: str | None = None,
    ) -> dict[str, Any]:
        if action not in {"start", "stop", "remove", "destroy"}:
            raise NephosError(
                "unsupported_lifecycle_action",
                "Unsupported Service lifecycle action.",
                status_code=404,
                details={"serviceInstance": slug, "action": action},
            )
        slug = validate_machine_identifier(slug, field="serviceInstance")
        if action == "destroy":
            _validate_destroy_confirmation(slug=slug, confirm=confirm)

        now = utc_now()
        with connect(self.db_path) as connection, transaction(connection):
            row = self._service_row_for_update(connection, slug)
            impacts = self._dependent_impacts(connection, row["id"])
            if action in {"stop", "remove", "destroy"} and impacts and not force:
                raise NephosError(
                    "service_dependency_blocked",
                    "Service has dependent App instances; repeat with force to continue.",
                    status_code=409,
                    details={"serviceInstance": slug, "action": action, "impact": impacts},
                )

            if action == "destroy":
                should_increment = row["delete_requested_at"] is None
                if should_increment:
                    connection.execute(
                        """
                        UPDATE service_instances
                        SET delete_requested_at = ?,
                            generation = generation + 1,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (now, now, row["id"]),
                    )
            else:
                lifecycle = {"start": "running", "stop": "stopped", "remove": "removed"}[action]
                if row["lifecycle"] != lifecycle or row["delete_requested_at"] is not None:
                    connection.execute(
                        """
                        UPDATE service_instances
                        SET lifecycle = ?,
                            delete_requested_at = NULL,
                            generation = generation + 1,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (lifecycle, now, row["id"]),
                    )

            updated = connection.execute(
                "SELECT * FROM service_instances WHERE slug = ?",
                (slug,),
            ).fetchone()
            resource = self._service_snapshot(connection, updated)
            payload: dict[str, Any] = {"action": action, "force": force}
            if action == "destroy":
                payload["confirm"] = confirm
            if impacts:
                payload["impact"] = impacts
            reconciliation = _insert_reconciliation_request(
                connection,
                target_type="service_instance",
                target_id=resource["id"],
                target_generation=resource["generation"],
                action=f"service.{action}",
                payload=payload,
                target_snapshot=resource,
            )
            status = _upsert_status_snapshot(
                connection,
                _status_snapshot(
                    resource_type="service_instance",
                    resource_id=resource["id"],
                    lifecycle=resource["lifecycle"],
                    reason="reconciliation_pending",
                    message=_lifecycle_status_message("Service", action),
                    observed_generation=resource["generation"],
                ),
            )
            resource["status"] = status
        return {"resource": resource, "reconciliation": reconciliation, "status": status}

    def reconcile(self, *, slug: str) -> dict[str, Any]:
        slug = validate_machine_identifier(slug, field="serviceInstance")
        with connect(self.db_path) as connection, transaction(connection):
            row = self._service_row_for_update(connection, slug)
            resource = self._service_snapshot(connection, row)
            reconciliation = _insert_reconciliation_request(
                connection,
                target_type="service_instance",
                target_id=resource["id"],
                target_generation=resource["generation"],
                action="service.reconcile",
                payload={"manual": True},
                target_snapshot=resource,
            )
            status = _upsert_status_snapshot(
                connection,
                _status_snapshot(
                    resource_type="service_instance",
                    resource_id=resource["id"],
                    lifecycle=resource["lifecycle"],
                    reason="manual_reconciliation_requested",
                    message=_lifecycle_status_message("Service", "reconcile"),
                    observed_generation=resource["generation"],
                ),
            )
            resource["status"] = status
        return {"resource": resource, "reconciliation": reconciliation, "status": status}

    def _service_row_for_update(self, connection: sqlite3.Connection, slug: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM service_instances WHERE slug = ?",
            (slug,),
        ).fetchone()
        if row is None:
            raise NephosError(
                "service_instance_not_found",
                "Service instance not found.",
                status_code=404,
                details={"serviceInstance": slug},
            )
        return row

    def _dependent_impacts(
        self,
        connection: sqlite3.Connection,
        service_id: str,
    ) -> list[dict[str, Any]]:
        rows = connection.execute(
            """
            SELECT
                b.id AS binding_id,
                b.alias AS binding_alias,
                b.capability AS capability,
                a.slug AS app_slug
            FROM bindings b
            JOIN app_instances a ON a.id = b.app_instance_id
            WHERE b.service_instance_id = ?
            ORDER BY a.slug ASC, b.alias ASC
            """,
            (service_id,),
        ).fetchall()
        return [
            {
                "requiresForce": True,
                "appInstance": row["app_slug"],
                "bindingId": row["binding_id"],
                "bindingAlias": row["binding_alias"],
                "capability": row["capability"],
            }
            for row in rows
        ]

    def _service_snapshot(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        *,
        provides: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        status_row = connection.execute(
            """
            SELECT * FROM status_snapshots
            WHERE resource_type = 'service_instance' AND resource_id = ?
            """,
            (row["id"],),
        ).fetchone()
        return _service_from_row(
            row,
            provides=provides if provides is not None else self._provides_for_row(row),
            dependents=self._dependents_for_row(connection, row),
            status=_status_from_row(status_row),
        )

    def _dependents_for_row(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
    ) -> list[dict[str, Any]]:
        binding_rows = connection.execute(
            """
            SELECT
                b.*,
                a.slug AS app_slug,
                a.lifecycle AS app_lifecycle,
                s.slug AS service_slug
            FROM bindings b
            JOIN app_instances a ON a.id = b.app_instance_id
            JOIN service_instances s ON s.id = b.service_instance_id
            WHERE b.service_instance_id = ?
            ORDER BY a.slug ASC, b.alias ASC
            """,
            (row["id"],),
        ).fetchall()
        dependents: list[dict[str, Any]] = []
        for binding_row in binding_rows:
            status_row = connection.execute(
                """
                SELECT * FROM status_snapshots
                WHERE resource_type = 'binding' AND resource_id = ?
                """,
                (binding_row["id"],),
            ).fetchone()
            dependents.append(
                {
                    "appInstance": binding_row["app_slug"],
                    "bindingId": binding_row["id"],
                    "bindingAlias": binding_row["alias"],
                    "capability": binding_row["capability"],
                    "lifecycle": binding_row["app_lifecycle"],
                    "status": _compact_status_from_row(status_row),
                }
            )
        return dependents

    def _provides_for_row(self, row: sqlite3.Row) -> list[dict[str, Any]]:
        return _service_provides_from_catalog(self.settings, row)


class BindingRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def db_path(self) -> Path:
        return self.settings.db_path

    def get_binding(self, *, binding_id: str) -> dict[str, Any]:
        with connect(self.db_path) as connection:
            row = self._binding_row(connection, binding_id)
            status_row = connection.execute(
                """
                SELECT * FROM status_snapshots
                WHERE resource_type = 'binding' AND resource_id = ?
                """,
                (binding_id,),
            ).fetchone()
            return _binding_from_row(row, _status_from_row(status_row))

    def reconcile(self, *, binding_id: str) -> dict[str, Any]:
        with connect(self.db_path) as connection, transaction(connection):
            row = self._binding_row(connection, binding_id)
            resource = _binding_from_row(row)
            reconciliation = _insert_reconciliation_request(
                connection,
                target_type="binding",
                target_id=binding_id,
                target_generation=row["generation"],
                action="binding.reconcile",
                payload={"manual": True},
                target_snapshot=resource,
            )
            status = _upsert_status_snapshot(
                connection,
                _status_snapshot(
                    resource_type="binding",
                    resource_id=binding_id,
                    reason="manual_reconciliation_requested",
                    message=_lifecycle_status_message("Binding", "reconcile"),
                    observed_generation=row["generation"],
                ),
            )
            resource["status"] = status
        return {"resource": resource, "reconciliation": reconciliation, "status": status}

    def _binding_row(self, connection: sqlite3.Connection, binding_id: str) -> sqlite3.Row:
        row = connection.execute(
            """
            SELECT
                b.*,
                a.slug AS app_slug,
                s.slug AS service_slug
            FROM bindings b
            JOIN app_instances a ON a.id = b.app_instance_id
            JOIN service_instances s ON s.id = b.service_instance_id
            WHERE b.id = ?
            """,
            (binding_id,),
        ).fetchone()
        if row is None:
            raise NephosError(
                "binding_not_found",
                "Binding not found.",
                status_code=404,
                details={"bindingId": binding_id},
            )
        return row


class PlatformDomainRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def db_path(self) -> Path:
        return self.settings.db_path

    def list_domains(self) -> list[dict[str, Any]]:
        with connect(self.db_path) as connection:
            rows = connection.execute(
                "SELECT * FROM platform_domains ORDER BY is_default DESC, name ASC"
            ).fetchall()
        return [_domain_from_row(row) for row in rows]

    def add_domain(self, *, name: str, domain: str, is_default: bool) -> dict[str, Any]:
        name = validate_machine_identifier(name, field="name")
        domain = validate_root_domain(domain)
        now = utc_now()
        domain_id = new_id("platform_domain")

        with connect(self.db_path) as connection, transaction(connection):
            if is_default:
                connection.execute(
                    "UPDATE platform_domains SET is_default = 0, updated_at = ?",
                    (now,),
                )
            try:
                connection.execute(
                    """
                    INSERT INTO platform_domains(
                        id,
                        name,
                        domain,
                        is_default,
                        generation,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, 1, ?, ?)
                    """,
                    (domain_id, name, domain, int(is_default), now, now),
                )
            except sqlite3.IntegrityError as exc:
                raise NephosError(
                    "platform_domain_conflict",
                    "Platform domain name or domain already exists.",
                    status_code=409,
                    details={"name": name, "domain": domain},
                ) from exc
            row = connection.execute(
                "SELECT * FROM platform_domains WHERE id = ?",
                (domain_id,),
            ).fetchone()
            resource = _domain_from_row(row)
            reconciliation = _insert_reconciliation_request(
                connection,
                target_type="platform_domain",
                target_id=domain_id,
                target_generation=resource["generation"],
                action="platform_domain.add",
                payload={"name": name, "domain": domain, "default": is_default},
                target_snapshot=resource,
            )
            status = _upsert_status_snapshot(
                connection,
                _status_snapshot(
                    resource_type="platform_domain",
                    resource_id=domain_id,
                    reason="reconciliation_pending",
                    message="Platform domain desired state was updated and awaits reconciliation.",
                    observed_generation=resource["generation"],
                ),
            )
        return {"resource": resource, "reconciliation": reconciliation, "status": status}

    def set_default(self, *, name: str) -> dict[str, Any]:
        name = validate_machine_identifier(name, field="name")
        now = utc_now()
        with connect(self.db_path) as connection, transaction(connection):
            row = connection.execute(
                "SELECT * FROM platform_domains WHERE name = ?",
                (name,),
            ).fetchone()
            if row is None:
                raise NephosError(
                    "platform_domain_not_found",
                    "Platform domain not found.",
                    status_code=404,
                    details={"name": name},
                )
            connection.execute("UPDATE platform_domains SET is_default = 0, updated_at = ?", (now,))
            connection.execute(
                """
                UPDATE platform_domains
                SET is_default = 1,
                    generation = generation + 1,
                    updated_at = ?
                WHERE name = ?
                """,
                (now, name),
            )
            updated = connection.execute(
                "SELECT * FROM platform_domains WHERE name = ?",
                (name,),
            ).fetchone()
            resource = _domain_from_row(updated)
            reconciliation = _insert_reconciliation_request(
                connection,
                target_type="platform_domain",
                target_id=resource["id"],
                target_generation=resource["generation"],
                action="platform_domain.set_default",
                payload={"name": name},
                target_snapshot=resource,
            )
            status = _upsert_status_snapshot(
                connection,
                _status_snapshot(
                    resource_type="platform_domain",
                    resource_id=resource["id"],
                    reason="reconciliation_pending",
                    message="Platform domain default changed and awaits reconciliation.",
                    observed_generation=resource["generation"],
                ),
            )
        return {"resource": resource, "reconciliation": reconciliation, "status": status}

    def reconcile(self) -> dict[str, Any]:
        with connect(self.db_path) as connection, transaction(connection):
            row = connection.execute(
                """
                SELECT * FROM platform_domains
                WHERE is_default = 1
                ORDER BY name ASC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                raise NephosError(
                    "platform_domain_not_configured",
                    "No default platform domain is configured.",
                    status_code=409,
                    details={"configured": False},
                )
            resource = _domain_from_row(row)
            reconciliation = _insert_reconciliation_request(
                connection,
                target_type="platform_domain",
                target_id=resource["id"],
                target_generation=resource["generation"],
                action="platform_domain.reconcile",
                payload={"manual": True},
                target_snapshot=resource,
            )
            status = _upsert_status_snapshot(
                connection,
                _status_snapshot(
                    resource_type="platform_domain",
                    resource_id=resource["id"],
                    reason="manual_reconciliation_requested",
                    message="Manual platform domain reconciliation was requested.",
                    observed_generation=resource["generation"],
                ),
            )
        return {"resource": resource, "reconciliation": reconciliation, "status": status}

    def remove(self, *, name: str) -> dict[str, Any]:
        name = validate_machine_identifier(name, field="name")
        with connect(self.db_path) as connection, transaction(connection):
            row = connection.execute(
                "SELECT * FROM platform_domains WHERE name = ?",
                (name,),
            ).fetchone()
            if row is None:
                raise NephosError(
                    "platform_domain_not_found",
                    "Platform domain not found.",
                    status_code=404,
                    details={"name": name},
                )
            resource = _domain_from_row(row)
            reconciliation = _insert_reconciliation_request(
                connection,
                target_type="platform_domain",
                target_id=resource["id"],
                target_generation=resource["generation"],
                action="platform_domain.remove",
                payload={"name": name},
                target_snapshot=resource,
            )
            connection.execute("DELETE FROM platform_domains WHERE id = ?", (resource["id"],))
        return {"resource": resource, "reconciliation": reconciliation}
