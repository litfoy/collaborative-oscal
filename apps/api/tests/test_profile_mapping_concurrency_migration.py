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


def test_profiles_and_mappings_concurrency_migration_backfill_constraints_and_downgrade(
    db_engine,
) -> None:
    schema = f"pm_concurrency_migration_{uuid4().hex}"
    tenant_id = uuid4()
    profile_id = uuid4()
    collection_id = uuid4()
    actor_id = uuid4()

    profile_document = {
        "profile": {
            "uuid": str(uuid4()),
            "metadata": {
                "title": "Legacy profile",
                "last-modified": "2026-01-01T00:00:00Z",
                "version": "1.0.0",
                "oscal-version": "1.2.1",
            },
            "imports": [],
        }
    }
    mapping_document = {
        "mapping-collection": {
            "uuid": str(uuid4()),
            "metadata": {
                "title": "Legacy mapping",
                "last-modified": "2026-01-01T00:00:00Z",
                "version": "1.0.0",
                "oscal-version": "1.2.1",
            },
            "provenance": {
                "method": "human",
                "matching-rationale": "semantic",
                "status": "draft",
                "mapping-description": "legacy",
            },
            "mappings": [],
        }
    }

    with db_engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
            config = Config(str(Path(__file__).parents[3] / "alembic.ini"))
            config.attributes["connection"] = connection

            command.upgrade(config, "a91f6c2d4e8b")
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
                    "INSERT INTO profiles (id,tenant_id,title,document,created_at,updated_at) "
                    "VALUES "
                    "(:profile,:tenant,'Legacy profile',CAST(:document AS jsonb),now(),now())"
                ),
                {
                    "profile": profile_id,
                    "tenant": tenant_id,
                    "document": json.dumps(profile_document),
                },
            )
            connection.execute(
                text(
                    "INSERT INTO mapping_collections "
                    "(id,tenant_id,document,created_by,updated_by,created_at,updated_at) "
                    "VALUES "
                    "(:collection,:tenant,CAST(:document AS jsonb),:actor,:actor,now(),now())"
                ),
                {
                    "collection": collection_id,
                    "tenant": tenant_id,
                    "actor": actor_id,
                    "document": json.dumps(mapping_document),
                },
            )

            command.upgrade(config, "b62f4d1a9c3e")

            profile_version = connection.execute(
                text("SELECT concurrency_version FROM profiles WHERE id = :profile"),
                {"profile": profile_id},
            ).scalar_one()
            mapping_version = connection.execute(
                text(
                    "SELECT concurrency_version FROM mapping_collections "
                    "WHERE id = :collection"
                ),
                {"collection": collection_id},
            ).scalar_one()
            assert int(profile_version) == 1
            assert int(mapping_version) == 1

            profile_constraint = connection.execute(
                text(
                    "SELECT 1 "
                    "FROM pg_constraint c "
                    "JOIN pg_namespace n ON n.oid = c.connamespace "
                    "WHERE c.conname = 'ck_profiles_concurrency_version' "
                    "AND n.nspname = :schema"
                )
                ,
                {"schema": schema},
            ).scalar_one_or_none()
            mapping_constraint = connection.execute(
                text(
                    "SELECT 1 "
                    "FROM pg_constraint c "
                    "JOIN pg_namespace n ON n.oid = c.connamespace "
                    "WHERE c.conname = 'ck_mapping_collections_concurrency_version' "
                    "AND n.nspname = :schema"
                )
                ,
                {"schema": schema},
            ).scalar_one_or_none()
            assert profile_constraint == 1
            assert mapping_constraint == 1

            profile_savepoint = connection.begin_nested()
            with pytest.raises(IntegrityError):
                connection.execute(
                    text(
                        "UPDATE profiles SET concurrency_version = 0 WHERE id = :profile"
                    ),
                    {"profile": profile_id},
                )
            profile_savepoint.rollback()

            mapping_savepoint = connection.begin_nested()
            with pytest.raises(IntegrityError):
                connection.execute(
                    text(
                        "UPDATE mapping_collections SET concurrency_version = 0 "
                        "WHERE id = :collection"
                    ),
                    {"collection": collection_id},
                )
            mapping_savepoint.rollback()

            command.downgrade(config, "a91f6c2d4e8b")
            profile_columns = {
                column["name"] for column in connection.dialect.get_columns(connection, "profiles")
            }
            mapping_columns = {
                column["name"]
                for column in connection.dialect.get_columns(
                    connection, "mapping_collections"
                )
            }
            assert "concurrency_version" not in profile_columns
            assert "concurrency_version" not in mapping_columns
        finally:
            transaction.rollback()




