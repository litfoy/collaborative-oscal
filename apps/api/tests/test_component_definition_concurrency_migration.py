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


def test_component_definition_concurrency_migration_backfill_constraints_and_downgrade(
    db_engine,
) -> None:
    schema = f"component_concurrency_migration_{uuid4().hex}"
    tenant_id = uuid4()
    actor_id = uuid4()
    document_id = uuid4()

    component_document = {
        "component-definition": {
            "uuid": str(uuid4()),
            "metadata": {
                "title": "Legacy Component Definition",
                "last-modified": "2026-01-01T00:00:00Z",
                "version": "1.0.0",
                "oscal-version": "1.2.1",
            },
            "components": [
                {
                    "uuid": str(uuid4()),
                    "type": "policy",
                    "title": "Legacy component",
                    "description": "Legacy reusable guidance.",
                }
            ],
        }
    }

    with db_engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
            config = Config(str(Path(__file__).parents[3] / "alembic.ini"))
            config.attributes["connection"] = connection

            command.upgrade(config, "c92e1b7d4f33")
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
                    "INSERT INTO component_definitions "
                    "(id,tenant_id,document,created_by,updated_by,created_at,updated_at) "
                    "VALUES "
                    "(:document,:tenant,CAST(:payload AS jsonb),:actor,:actor,now(),now())"
                ),
                {
                    "document": document_id,
                    "tenant": tenant_id,
                    "actor": actor_id,
                    "payload": json.dumps(component_document),
                },
            )

            command.upgrade(config, "e6a2f4c1d9b7")

            version = connection.execute(
                text(
                    "SELECT concurrency_version "
                    "FROM component_definitions WHERE id = :document"
                ),
                {"document": document_id},
            ).scalar_one()
            assert int(version) == 1

            constraint = connection.execute(
                text(
                    "SELECT 1 "
                    "FROM pg_constraint c "
                    "JOIN pg_namespace n ON n.oid = c.connamespace "
                    "WHERE c.conname = 'ck_component_definitions_concurrency_version' "
                    "AND n.nspname = :schema"
                ),
                {"schema": schema},
            ).scalar_one_or_none()
            assert constraint == 1

            savepoint = connection.begin_nested()
            with pytest.raises(IntegrityError):
                connection.execute(
                    text(
                        "UPDATE component_definitions "
                        "SET concurrency_version = 0 WHERE id = :document"
                    ),
                    {"document": document_id},
                )
            savepoint.rollback()

            command.downgrade(config, "c92e1b7d4f33")
            columns = {
                column["name"]
                for column in connection.dialect.get_columns(
                    connection,
                    "component_definitions",
                )
            }
            assert "concurrency_version" not in columns
        finally:
            transaction.rollback()

