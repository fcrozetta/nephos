from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import cast

from nephos_api.db import connect_database, utc_now
from nephos_api.domain import (
    AdminAccount,
    AppInstance,
    Binding,
    PlatformDomain,
    ReconciliationRequest,
    ServiceInstance,
    StatusSnapshot,
    generate_id,
    validate_dns_suffix,
    validate_machine_identifier,
)


class DesiredStateRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    @contextmanager
    def transaction(self, *, immediate: bool = False) -> Iterator[StateTransaction]:
        # ``immediate`` acquires the write lock at BEGIN so a check-then-insert
        # (e.g. the zero-admin guard) cannot race a concurrent writer that read
        # the same pre-insert state.
        connection = connect_database(self.db_path)
        try:
            connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            yield StateTransaction(connection)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def count_admin_accounts(self) -> int:
        with connect_database(self.db_path) as connection:
            row = connection.execute(
                "SELECT count(*) AS count FROM admin_accounts"
            ).fetchone()
        return int(row["count"])

    def get_admin_credentials(self, username: str) -> dict[str, object] | None:
        with connect_database(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT id, username, password_hash
                FROM admin_accounts
                WHERE username = ?
                """,
                (username,),
            ).fetchone()
        return dict(row) if row else None

    def list_platform_domains(self) -> list[PlatformDomain]:
        with connect_database(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT id, name, domain, is_default, generation, created_at, updated_at
                FROM platform_domains
                ORDER BY name
                """
            ).fetchall()
        return [
            PlatformDomain(
                id=row["id"],
                name=row["name"],
                domain=row["domain"],
                is_default=bool(row["is_default"]),
                generation=row["generation"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def list_app_rows(self) -> list[dict[str, object]]:
        with connect_database(self.db_path) as connection:
            rows = connection.execute(
                "SELECT * FROM app_instances ORDER BY slug"
            ).fetchall()
        return [dict(row) for row in rows]

    def list_service_rows(self) -> list[dict[str, object]]:
        with connect_database(self.db_path) as connection:
            rows = connection.execute(
                "SELECT * FROM service_instances ORDER BY slug"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_app_row(self, slug: str) -> dict[str, object] | None:
        with connect_database(self.db_path) as connection:
            row = connection.execute(
                "SELECT * FROM app_instances WHERE slug = ?",
                (slug,),
            ).fetchone()
        return dict(row) if row else None

    def get_service_row(self, slug: str) -> dict[str, object] | None:
        with connect_database(self.db_path) as connection:
            row = connection.execute(
                "SELECT * FROM service_instances WHERE slug = ?",
                (slug,),
            ).fetchone()
        return dict(row) if row else None

    def list_bindings_for_app(self, app_instance_id: str) -> list[dict[str, object]]:
        with connect_database(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    bindings.id,
                    bindings.alias,
                    bindings.capability,
                    bindings.protocol,
                    bindings.output_summary_json,
                    app_instances.slug AS app_instance_slug,
                    service_instances.id AS service_instance_id,
                    service_instances.slug AS service_instance_slug
                FROM bindings
                JOIN app_instances
                    ON app_instances.id = bindings.app_instance_id
                JOIN service_instances
                    ON service_instances.id = bindings.service_instance_id
                WHERE bindings.app_instance_id = ?
                ORDER BY bindings.alias
                """,
                (app_instance_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_binding_rows(self) -> list[dict[str, object]]:
        with connect_database(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    bindings.id,
                    bindings.alias,
                    bindings.capability,
                    bindings.protocol,
                    bindings.generation,
                    bindings.output_summary_json,
                    bindings.created_at,
                    bindings.updated_at,
                    app_instances.id AS app_instance_id,
                    app_instances.generation AS app_instance_generation,
                    app_instances.slug AS app_instance_slug,
                    service_instances.id AS service_instance_id,
                    service_instances.slug AS service_instance_slug
                FROM bindings
                JOIN app_instances
                    ON app_instances.id = bindings.app_instance_id
                JOIN service_instances
                    ON service_instances.id = bindings.service_instance_id
                ORDER BY app_instances.slug, bindings.alias
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_binding_row(self, binding_id: str) -> dict[str, object] | None:
        with connect_database(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT
                    bindings.id,
                    bindings.alias,
                    bindings.capability,
                    bindings.protocol,
                    bindings.generation,
                    bindings.output_summary_json,
                    bindings.created_at,
                    bindings.updated_at,
                    app_instances.id AS app_instance_id,
                    app_instances.generation AS app_instance_generation,
                    app_instances.slug AS app_instance_slug,
                    service_instances.id AS service_instance_id,
                    service_instances.slug AS service_instance_slug
                FROM bindings
                JOIN app_instances
                    ON app_instances.id = bindings.app_instance_id
                JOIN service_instances
                    ON service_instances.id = bindings.service_instance_id
                WHERE bindings.id = ?
                """,
                (binding_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_status_snapshot(
        self,
        *,
        resource_type: str,
        resource_id: str,
    ) -> dict[str, object] | None:
        with connect_database(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM status_snapshots
                WHERE resource_type = ?
                    AND resource_id = ?
                """,
                (resource_type, resource_id),
            ).fetchone()
        return dict(row) if row else None

    def list_dependents_for_service(
        self,
        service_instance_id: str,
    ) -> list[dict[str, object]]:
        with connect_database(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    app_instances.slug AS app_instance_slug,
                    app_instances.lifecycle AS app_lifecycle,
                    app_instances.delete_requested_at AS app_delete_requested_at,
                    bindings.id AS binding_id,
                    bindings.alias AS binding_alias,
                    bindings.capability,
                    bindings.protocol
                FROM bindings
                JOIN app_instances
                    ON app_instances.id = bindings.app_instance_id
                WHERE bindings.service_instance_id = ?
                ORDER BY app_instances.slug, bindings.alias
                """,
                (service_instance_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def claim_next_reconciliation_request(self) -> dict[str, object] | None:
        with connect_database(self.db_path) as connection:
            connection.execute("BEGIN")
            row = connection.execute(
                """
                SELECT *
                FROM reconciliation_requests
                WHERE state = 'pending'
                ORDER BY created_at
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                connection.rollback()
                return None

            now = utc_now()
            connection.execute(
                """
                UPDATE reconciliation_requests
                SET state = 'running',
                    updated_at = ?
                WHERE id = ?
                """,
                (now, row["id"]),
            )
            updated = connection.execute(
                "SELECT * FROM reconciliation_requests WHERE id = ?",
                (row["id"],),
            ).fetchone()
            connection.commit()
        return dict(updated)


class StateTransaction:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def create_app_instance(
        self,
        *,
        slug: str,
        catalog_name: str,
        catalog_source_id: str,
        catalog_source_path: str,
        manifest_digest: str,
        catalog_version: str | None = None,
        config: Mapping[str, object] | None = None,
        lifecycle: str = "running",
    ) -> AppInstance:
        return cast(
            AppInstance,
            self._create_instance(
                table="app_instances",
                catalog_kind="App",
                id_prefix="appinst",
                instance_type=AppInstance,
                slug=slug,
                catalog_name=catalog_name,
                catalog_source_id=catalog_source_id,
                catalog_source_path=catalog_source_path,
                manifest_digest=manifest_digest,
                catalog_version=catalog_version,
                config=config,
                lifecycle=lifecycle,
            ),
        )

    def create_service_instance(
        self,
        *,
        slug: str,
        catalog_name: str,
        catalog_source_id: str,
        catalog_source_path: str,
        manifest_digest: str,
        catalog_version: str | None = None,
        config: Mapping[str, object] | None = None,
        lifecycle: str = "running",
    ) -> ServiceInstance:
        return cast(
            ServiceInstance,
            self._create_instance(
                table="service_instances",
                catalog_kind="Service",
                id_prefix="svcinst",
                instance_type=ServiceInstance,
                slug=slug,
                catalog_name=catalog_name,
                catalog_source_id=catalog_source_id,
                catalog_source_path=catalog_source_path,
                manifest_digest=manifest_digest,
                catalog_version=catalog_version,
                config=config,
                lifecycle=lifecycle,
            ),
        )

    def _create_instance(
        self,
        *,
        table: str,
        catalog_kind: str,
        id_prefix: str,
        instance_type: type[AppInstance] | type[ServiceInstance],
        slug: str,
        catalog_name: str,
        catalog_source_id: str,
        catalog_source_path: str,
        manifest_digest: str,
        catalog_version: str | None,
        config: Mapping[str, object] | None,
        lifecycle: str,
    ) -> AppInstance | ServiceInstance:
        validate_machine_identifier(slug)
        now = utc_now()
        instance = instance_type(
            id=generate_id(id_prefix),
            slug=slug,
            lifecycle=lifecycle,
            generation=1,
        )
        self._connection.execute(
            f"""
            INSERT INTO {table}(
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
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                instance.id,
                instance.slug,
                catalog_kind,
                catalog_name,
                catalog_version,
                catalog_source_id,
                catalog_source_path,
                manifest_digest,
                instance.lifecycle,
                instance.generation,
                _json_object(config),
                now,
                now,
            ),
        )
        return instance

    def create_binding(
        self,
        *,
        app_instance_id: str,
        service_instance_id: str,
        alias: str,
        capability: str,
        protocol: str | None = None,
        output_summary: Mapping[str, object] | None = None,
    ) -> Binding:
        validate_machine_identifier(alias)
        now = utc_now()
        binding = Binding(
            id=generate_id("binding"),
            alias=alias,
            capability=capability,
            protocol=protocol,
            generation=1,
        )
        self._connection.execute(
            """
            INSERT INTO bindings(
                id,
                app_instance_id,
                service_instance_id,
                alias,
                capability,
                protocol,
                generation,
                output_summary_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                binding.id,
                app_instance_id,
                service_instance_id,
                binding.alias,
                binding.capability,
                binding.protocol,
                binding.generation,
                _json_object(output_summary),
                now,
                now,
            ),
        )
        return binding

    def count_admin_accounts(self) -> int:
        row = self._connection.execute(
            "SELECT count(*) AS count FROM admin_accounts"
        ).fetchone()
        return int(row["count"])

    def create_admin_account(
        self,
        *,
        username: str,
        password_hash: str,
    ) -> AdminAccount:
        now = utc_now()
        account = AdminAccount(
            id=generate_id("admin"),
            username=username,
            created_at=now,
            updated_at=now,
        )
        self._connection.execute(
            """
            INSERT INTO admin_accounts(
                id,
                username,
                password_hash,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                account.id,
                account.username,
                password_hash,
                now,
                now,
            ),
        )
        return account

    def create_platform_domain(
        self,
        *,
        name: str,
        domain: str,
        is_default: bool,
    ) -> PlatformDomain:
        validate_machine_identifier(name)
        validate_dns_suffix(domain)
        now = utc_now()
        platform_domain = PlatformDomain(
            id=generate_id("domain"),
            name=name,
            domain=domain,
            is_default=is_default,
            generation=1,
            created_at=now,
            updated_at=now,
        )
        self._connection.execute(
            """
            INSERT INTO platform_domains(
                id,
                name,
                domain,
                is_default,
                generation,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                platform_domain.id,
                platform_domain.name,
                platform_domain.domain,
                1 if platform_domain.is_default else 0,
                platform_domain.generation,
                now,
                now,
            ),
        )
        return platform_domain

    def count_platform_domains(self) -> int:
        row = self._connection.execute(
            "SELECT count(*) AS count FROM platform_domains"
        ).fetchone()
        return int(row["count"])

    def clear_default_platform_domains(self) -> None:
        now = utc_now()
        self._connection.execute(
            """
            UPDATE platform_domains
            SET is_default = 0,
                generation = generation + 1,
                updated_at = ?
            WHERE is_default = 1
            """,
            (now,),
        )

    def get_platform_domain_by_name(self, name: str) -> PlatformDomain | None:
        row = self._connection.execute(
            """
            SELECT id, name, domain, is_default, generation, created_at, updated_at
            FROM platform_domains
            WHERE name = ?
            """,
            (name,),
        ).fetchone()
        if row is None:
            return None
        return PlatformDomain(
            id=row["id"],
            name=row["name"],
            domain=row["domain"],
            is_default=bool(row["is_default"]),
            generation=row["generation"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def set_default_platform_domain(self, name: str) -> PlatformDomain:
        self.clear_default_platform_domains()
        now = utc_now()
        self._connection.execute(
            """
            UPDATE platform_domains
            SET is_default = 1,
                generation = generation + 1,
                updated_at = ?
            WHERE name = ?
            """,
            (now, name),
        )
        domain = self.get_platform_domain_by_name(name)
        if domain is None:
            raise KeyError(name)
        return domain

    def remove_platform_domain(self, name: str) -> PlatformDomain:
        domain = self.get_platform_domain_by_name(name)
        if domain is None:
            raise KeyError(name)
        self._connection.execute(
            "DELETE FROM platform_domains WHERE name = ?",
            (name,),
        )
        return domain

    def upsert_status_snapshot(
        self,
        *,
        resource_type: str,
        resource_id: str,
        level: str,
        lifecycle: str | None = None,
        reconciliation: str | None = None,
        reason: str | None = None,
        message: str | None = None,
        evidence: Sequence[Mapping[str, object]] | None = None,
        observed_generation: int | None = None,
    ) -> StatusSnapshot:
        now = utc_now()
        status = StatusSnapshot(
            id=generate_id("status"),
            resource_type=resource_type,
            resource_id=resource_id,
            level=level,
        )
        self._connection.execute(
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
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(resource_type, resource_id) DO UPDATE SET
                id = excluded.id,
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
                status.id,
                status.resource_type,
                status.resource_id,
                status.level,
                lifecycle,
                reconciliation,
                reason,
                message,
                _json_array(evidence),
                observed_generation,
                now,
                now,
                now,
            ),
        )
        return status

    def create_reconciliation_request(
        self,
        *,
        target_type: str,
        target_id: str,
        target_generation: int,
        action: str,
        payload: Mapping[str, object] | None = None,
        target_snapshot: Mapping[str, object] | None = None,
    ) -> ReconciliationRequest:
        now = utc_now()
        request = ReconciliationRequest(
            id=generate_id("reconcile"),
            target_type=target_type,
            target_id=target_id,
            target_generation=target_generation,
            action=action,
            state="pending",
        )
        self._connection.execute(
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
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request.id,
                request.target_type,
                request.target_id,
                request.target_generation,
                request.action,
                _json_object(payload),
                _json_object(target_snapshot),
                request.state,
                now,
                now,
            ),
        )
        return request

    def create_reconciliation_request_if_not_active(
        self,
        *,
        target_type: str,
        target_id: str,
        target_generation: int,
        action: str,
        payload: Mapping[str, object] | None = None,
        target_snapshot: Mapping[str, object] | None = None,
    ) -> ReconciliationRequest:
        row = self._connection.execute(
            """
            SELECT id, target_type, target_id, target_generation, action, state
            FROM reconciliation_requests
            WHERE target_type = ?
                AND target_id = ?
                AND target_generation = ?
                AND action = ?
                AND state IN ('pending', 'running')
            ORDER BY created_at
            LIMIT 1
            """,
            (target_type, target_id, target_generation, action),
        ).fetchone()
        if row is not None:
            return ReconciliationRequest(
                id=row["id"],
                target_type=row["target_type"],
                target_id=row["target_id"],
                target_generation=row["target_generation"],
                action=row["action"],
                state=row["state"],
            )
        return self.create_reconciliation_request(
            target_type=target_type,
            target_id=target_id,
            target_generation=target_generation,
            action=action,
            payload=payload,
            target_snapshot=target_snapshot,
        )

    def update_service_lifecycle(
        self,
        *,
        slug: str,
        lifecycle: str,
    ) -> dict[str, object]:
        return self._update_lifecycle(
            table="service_instances",
            slug=slug,
            lifecycle=lifecycle,
        )

    def update_app_lifecycle(
        self,
        *,
        slug: str,
        lifecycle: str,
    ) -> dict[str, object]:
        return self._update_lifecycle(
            table="app_instances",
            slug=slug,
            lifecycle=lifecycle,
        )

    def _update_lifecycle(
        self,
        *,
        table: str,
        slug: str,
        lifecycle: str,
    ) -> dict[str, object]:
        now = utc_now()
        self._connection.execute(
            f"""
            UPDATE {table}
            SET lifecycle = ?,
                generation = generation + 1,
                updated_at = ?
            WHERE slug = ?
            """,
            (lifecycle, now, slug),
        )
        return self._row_by_slug(table=table, slug=slug)

    def mark_service_delete_requested(self, *, slug: str) -> dict[str, object]:
        return self._mark_delete_requested(table="service_instances", slug=slug)

    def mark_app_delete_requested(self, *, slug: str) -> dict[str, object]:
        return self._mark_delete_requested(table="app_instances", slug=slug)

    def update_binding_output_summary(
        self,
        *,
        binding_id: str,
        output_summary: Mapping[str, object],
    ) -> None:
        now = utc_now()
        self._connection.execute(
            """
            UPDATE bindings
            SET output_summary_json = ?,
                generation = generation + 1,
                updated_at = ?
            WHERE id = ?
            """,
            (_json_object(output_summary), now, binding_id),
        )

    def delete_service_instance(self, *, instance_id: str) -> None:
        self._connection.execute(
            "DELETE FROM bindings WHERE service_instance_id = ?",
            (instance_id,),
        )
        self._connection.execute(
            "DELETE FROM service_instances WHERE id = ?",
            (instance_id,),
        )

    def delete_app_instance(self, *, instance_id: str) -> None:
        self._connection.execute(
            "DELETE FROM bindings WHERE app_instance_id = ?",
            (instance_id,),
        )
        self._connection.execute(
            "DELETE FROM app_instances WHERE id = ?",
            (instance_id,),
        )

    def _mark_delete_requested(self, *, table: str, slug: str) -> dict[str, object]:
        now = utc_now()
        self._connection.execute(
            f"""
            UPDATE {table}
            SET delete_requested_at = ?,
                generation = generation + 1,
                updated_at = ?
            WHERE slug = ?
            """,
            (now, now, slug),
        )
        return self._row_by_slug(table=table, slug=slug)

    def _row_by_slug(self, *, table: str, slug: str) -> dict[str, object]:
        row = self._connection.execute(
            f"SELECT * FROM {table} WHERE slug = ?",
            (slug,),
        ).fetchone()
        if row is None:
            raise KeyError(slug)
        return dict(row)

    def update_reconciliation_request_state(
        self,
        *,
        request_id: str,
        state: str,
        error: str | None = None,
    ) -> None:
        now = utc_now()
        self._connection.execute(
            """
            UPDATE reconciliation_requests
            SET state = ?,
                error = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (state, error, now, request_id),
        )


def _json_object(value: Mapping[str, object] | None) -> str:
    return json.dumps({} if value is None else value, sort_keys=True)


def _json_array(value: Sequence[Mapping[str, object]] | None) -> str:
    return json.dumps([] if value is None else value, sort_keys=True)
