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


def test_implementation_concurrency_migration_backfill_constraints_and_downgrade(
    db_engine,
) -> None:
    schema = f"implementation_concurrency_migration_{uuid4().hex}"
    tenant_id = uuid4()
    actor_id = uuid4()
    catalog_id = uuid4()
    revision_id = uuid4()
    control_index_id = uuid4()
    implementation_id = uuid4()

    with db_engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
            config = Config(str(Path(__file__).parents[3] / "alembic.ini"))
            config.attributes["connection"] = connection

            command.upgrade(config, "a4b9e8c7d6f1")
            connection.execute(
                text(
                    "INSERT INTO tenants (id,name,slug,created_at,updated_at) "
                    "VALUES (:id,'Tenant','tenant',now(),now())"
                ),
                {"id": tenant_id},
            )
            connection.execute(
                text(
                    "INSERT INTO user_identities "
                    "(id,issuer,subject,display_name,email,created_at,updated_at) "
                    "VALUES "
                    "(:id,'https://issuer.example.test','migration-user',"
                    "'Migration User',NULL,now(),now())"
                ),
                {"id": actor_id},
            )
            connection.execute(
                text(
                    "INSERT INTO catalogs "
                    "(id,tenant_id,name,description,origin_type,source_uri,"
                    "source_organization,license_identifier,created_at,updated_at) "
                    "VALUES "
                    "(:id,:tenant,'Catalog',NULL,'custom',NULL,NULL,NULL,now(),now())"
                ),
                {"id": catalog_id, "tenant": tenant_id},
            )
            connection.execute(
                text(
                    "INSERT INTO catalog_revisions "
                    "(id,tenant_id,catalog_id,revision_number,lifecycle_status,"
                    "oscal_document_uuid,oscal_version,source_version,source_format,"
                    "content_sha256,content,created_at,updated_at,published_at) "
                    "VALUES "
                    "(:id,:tenant,:catalog,1,'draft',:doc_uuid,'1.2.1',NULL,NULL,"
                    ":sha,CAST(:content AS jsonb),now(),now(),NULL)"
                ),
                {
                    "id": revision_id,
                    "tenant": tenant_id,
                    "catalog": catalog_id,
                    "doc_uuid": uuid4(),
                    "sha": "a" * 64,
                    "content": json.dumps(
                        {
                            "catalog": {
                                "uuid": str(uuid4()),
                                "metadata": {
                                    "title": "Catalog",
                                    "last-modified": "2026-01-01T00:00:00Z",
                                    "version": "1.0",
                                    "oscal-version": "1.2.1",
                                },
                                "controls": [{"id": "ac-1", "title": "Access control"}],
                            }
                        }
                    ),
                },
            )
            connection.execute(
                text(
                    "INSERT INTO catalog_control_indexes "
                    "(id,tenant_id,catalog_revision_id,oscal_control_id,"
                    "parent_control_id,group_id,title,structural_path,display_order) "
                    "VALUES "
                    "(:id,:tenant,:revision,'ac-1',NULL,NULL,'Access control',"
                    "'/catalog/controls/0',0)"
                ),
                {
                    "id": control_index_id,
                    "tenant": tenant_id,
                    "revision": revision_id,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO control_implementations "
                    "(id,tenant_id,organization_id,system_id,system_component_id,"
                    "profile_id,profile_import_id,catalog_id,revision_id,"
                    "oscal_control_id,description,status,oscal_implementation_status,"
                    "oscal_status_explanation,evidence_references,created_by,"
                    "updated_by,created_at,updated_at) "
                    "VALUES "
                    "(:id,:tenant,NULL,NULL,NULL,NULL,NULL,:catalog,:revision,'ac-1',"
                    "'Legacy','in_progress',NULL,NULL,CAST(:evidence AS jsonb),"
                    ":actor,:actor,now(),now())"
                ),
                {
                    "id": implementation_id,
                    "tenant": tenant_id,
                    "catalog": catalog_id,
                    "revision": revision_id,
                    "evidence": json.dumps(["document:legacy"]),
                    "actor": actor_id,
                },
            )

            command.upgrade(config, "c1a5f9e8d2b4")

            version = connection.execute(
                text(
                    "SELECT concurrency_version "
                    "FROM control_implementations WHERE id = :implementation"
                ),
                {"implementation": implementation_id},
            ).scalar_one()
            assert int(version) == 1

            constraint = connection.execute(
                text(
                    "SELECT 1 "
                    "FROM pg_constraint c "
                    "JOIN pg_namespace n ON n.oid = c.connamespace "
                    "WHERE c.conname = 'ck_implementations_concurrency_version' "
                    "AND n.nspname = :schema"
                ),
                {"schema": schema},
            ).scalar_one_or_none()
            assert constraint == 1

            savepoint = connection.begin_nested()
            with pytest.raises(IntegrityError):
                connection.execute(
                    text(
                        "UPDATE control_implementations "
                        "SET concurrency_version = 0 "
                        "WHERE id = :implementation"
                    ),
                    {"implementation": implementation_id},
                )
            savepoint.rollback()

            command.downgrade(config, "a4b9e8c7d6f1")
            columns = {
                column["name"]
                for column in connection.dialect.get_columns(
                    connection,
                    "control_implementations",
                )
            }
            assert "concurrency_version" not in columns
        finally:
            transaction.rollback()



