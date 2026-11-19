# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration


def test_system_and_component_concurrency_migration_backfill_constraints_and_downgrade(
    db_engine,
) -> None:
    schema = f"system_component_concurrency_{uuid4().hex}"
    tenant_id = uuid4()
    actor_id = uuid4()
    system_id = uuid4()
    component_id = uuid4()
    component_uuid = uuid4()

    with db_engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
            config = Config(str(Path(__file__).parents[3] / "alembic.ini"))
            config.attributes["connection"] = connection

            command.upgrade(config, "e6a2f4c1d9b7")
            connection.execute(
                text(
                    "INSERT INTO tenants (id,name,slug,created_at,updated_at) "
                    "VALUES (:tenant,'Tenant','tenant',now(),now())"
                ),
                {"tenant": tenant_id},
            )
            connection.execute(
                text(
                    "INSERT INTO user_identities "
                    "(id,issuer,subject,display_name,email,created_at,updated_at) "
                    "VALUES "
                    "(:actor,'https://issuer.example.test','legacy-author',"
                    "'Legacy Author',NULL,now(),now())"
                ),
                {"actor": actor_id},
            )
            connection.execute(
                text(
                    "INSERT INTO information_systems "
                    "(id,tenant_id,organization_id,name,description,system_boundary,system_ids,"
                    "information_types,operational_status,status_remarks,"
                    "security_sensitivity_level,created_by,updated_by,created_at,updated_at) "
                    "VALUES "
                    "(:system,:tenant,NULL,'Legacy system','Legacy description','Legacy boundary',"
                    "CAST(:system_ids AS jsonb),CAST(:information_types AS jsonb),"
                    "'operational',NULL,NULL,:actor,:actor,now(),now())"
                ),
                {
                    "system": system_id,
                    "tenant": tenant_id,
                    "actor": actor_id,
                    "system_ids": json.dumps([{"id": "legacy-system-id"}]),
                    "information_types": json.dumps(
                        [
                            {
                                "uuid": str(uuid4()),
                                "title": "Legacy information",
                                "description": "Legacy information description.",
                            }
                        ]
                    ),
                },
            )
            connection.execute(
                text(
                    "INSERT INTO system_components "
                    "(id,tenant_id,system_id,oscal_component_uuid,source_snapshot_id,"
                    "source_component_uuid,is_system_component,component,"
                    "created_by,updated_by,created_at,updated_at) "
                    "VALUES "
                    "(:component,:tenant,:system,:oscal_uuid,NULL,NULL,FALSE,"
                    "CAST(:component_json AS jsonb),:actor,:actor,now(),now())"
                ),
                {
                    "component": component_id,
                    "tenant": tenant_id,
                    "system": system_id,
                    "oscal_uuid": component_uuid,
                    "actor": actor_id,
                    "component_json": json.dumps(
                        {
                            "uuid": str(component_uuid),
                            "type": "service",
                            "title": "Legacy component",
                            "description": "Legacy component description.",
                            "status": {"state": "operational"},
                        }
                    ),
                },
            )

            command.upgrade(config, "a4b9e8c7d6f1")

            system_version = connection.execute(
                text(
                    "SELECT concurrency_version FROM information_systems WHERE id = :system"
                ),
                {"system": system_id},
            ).scalar_one()
            component_version = connection.execute(
                text(
                    "SELECT concurrency_version FROM system_components WHERE id = :component"
                ),
                {"component": component_id},
            ).scalar_one()
            assert int(system_version) == 1
            assert int(component_version) == 1

            system_constraint = connection.execute(
                text(
                    "SELECT 1 "
                    "FROM pg_constraint c "
                    "JOIN pg_namespace n ON n.oid = c.connamespace "
                    "WHERE c.conname = 'ck_information_systems_concurrency_version' "
                    "AND n.nspname = :schema"
                ),
                {"schema": schema},
            ).scalar_one_or_none()
            component_constraint = connection.execute(
                text(
                    "SELECT 1 "
                    "FROM pg_constraint c "
                    "JOIN pg_namespace n ON n.oid = c.connamespace "
                    "WHERE c.conname = 'ck_system_components_concurrency_version' "
                    "AND n.nspname = :schema"
                ),
                {"schema": schema},
            ).scalar_one_or_none()
            assert system_constraint == 1
            assert component_constraint == 1

            system_savepoint = connection.begin_nested()
            with pytest.raises(IntegrityError):
                connection.execute(
                    text(
                        "UPDATE information_systems SET concurrency_version = 0 "
                        "WHERE id = :system"
                    ),
                    {"system": system_id},
                )
            system_savepoint.rollback()

            component_savepoint = connection.begin_nested()
            with pytest.raises(IntegrityError):
                connection.execute(
                    text(
                        "UPDATE system_components SET concurrency_version = 0 "
                        "WHERE id = :component"
                    ),
                    {"component": component_id},
                )
            component_savepoint.rollback()

            command.downgrade(config, "e6a2f4c1d9b7")
            system_columns = {
                column["name"]
                for column in connection.dialect.get_columns(connection, "information_systems")
            }
            component_columns = {
                column["name"]
                for column in connection.dialect.get_columns(connection, "system_components")
            }
            assert "concurrency_version" not in system_columns
            assert "concurrency_version" not in component_columns
        finally:
            transaction.rollback()


