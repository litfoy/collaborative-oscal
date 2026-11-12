import json
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from collaborative_oscal_oscal.profile import build_profile_document
from sqlalchemy import text

pytestmark = pytest.mark.integration


def test_existing_profile_and_implementation_survive_migration(db_engine) -> None:
    tenant, catalog, revision, profile, implementation, user, control, responsibility = [
        uuid4() for _ in range(8)
    ]
    schema = f"profile_migration_{uuid4().hex}"
    document = build_profile_document(
        profile_uuid=uuid4(),
        title="Old profile",
        oscal_version="1.2.1",
        catalog_href=f"/api/v1/tenants/{tenant}/catalogs/{catalog}/revisions/{revision}/export",
        control_ids=["ac-1", "ac-2"],
        description="Retained purpose",
    )
    with db_engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
            config = Config(str(Path(__file__).parents[3] / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "4d7e8f901abc")
            args = {
                "tenant": tenant,
                "catalog": catalog,
                "revision": revision,
                "profile": profile,
                "implementation": implementation,
                "user": user,
                "control": control,
                "responsibility": responsibility,
                "document": json.dumps(document),
                "catalog_uuid": uuid4(),
                "membership": uuid4(),
            }
            statements = [
                "INSERT INTO tenants (id,name,slug,created_at,updated_at) "
                "VALUES (:tenant,'Tenant','test',now(),now())",
                "INSERT INTO catalogs (id,tenant_id,name,origin_type,created_at,updated_at) "
                "VALUES (:catalog,:tenant,'Catalog','custom',now(),now())",
                "INSERT INTO catalog_revisions (id,tenant_id,catalog_id,revision_number,"
                "lifecycle_status,oscal_document_uuid,oscal_version,content_sha256,content,"
                "created_at,updated_at) VALUES (:revision,:tenant,:catalog,1,'draft',"
                ":catalog_uuid,'1.2.1',repeat('0',64),'{}',now(),now())",
                "INSERT INTO catalog_control_indexes (id,tenant_id,catalog_revision_id,"
                "oscal_control_id,title,structural_path,display_order) "
                "VALUES (:control,:tenant,:revision,'ac-1','Control','/control',0)",
                "INSERT INTO user_identities (id,issuer,subject,created_at,updated_at) "
                "VALUES (:user,'https://identity.example','person',now(),now())",
                "INSERT INTO tenant_memberships (id,tenant_id,user_id,role,status,created_at,"
                "updated_at) VALUES (:membership,:tenant,:user,'viewer','active',now(),now())",
                "INSERT INTO profiles (id,tenant_id,catalog_id,revision_id,title,document,"
                "created_at,updated_at) VALUES (:profile,:tenant,:catalog,:revision,"
                "'Old profile',CAST(:document AS jsonb),now(),now())",
                "INSERT INTO control_implementations (id,tenant_id,profile_id,catalog_id,"
                "revision_id,oscal_control_id,description,status,evidence_references,"
                "created_by,updated_by,created_at,updated_at) VALUES (:implementation,:tenant,"
                ":profile,:catalog,:revision,'ac-1','Kept','implemented','[\"evidence\"]',"
                ":user,:user,now(),now())",
                "INSERT INTO implementation_responsibilities (id,tenant_id,implementation_id,"
                "kind,user_id,role) VALUES (:responsibility,:tenant,:implementation,"
                "'accountable',:user,'Owner')",
            ]
            for statement in statements:
                connection.execute(text(statement), args)
            command.upgrade(config, "head")
            stored = connection.execute(
                text("SELECT document FROM profiles WHERE id=:profile"), args
            ).scalar_one()
            source = (
                connection.execute(
                    text(
                        "SELECT id, catalog_id, revision_id, position, active FROM profile_imports "
                        "WHERE profile_id=:profile"
                    ),
                    args,
                )
                .mappings()
                .one()
            )
            record = (
                connection.execute(
                    text(
                        "SELECT id,profile_id,profile_import_id,catalog_id,revision_id,"
                        "oscal_control_id,"
                        "description,status,evidence_references FROM control_implementations "
                        "WHERE id=:implementation"
                    ),
                    args,
                )
                .mappings()
                .one()
            )
            assignment = (
                connection.execute(
                    text(
                        "SELECT id,user_id,role FROM implementation_responsibilities "
                        "WHERE id=:responsibility"
                    ),
                    args,
                )
                .mappings()
                .one()
            )
            assert stored == document
            assert (
                source["catalog_id"],
                source["revision_id"],
                source["position"],
                source["active"],
            ) == (catalog, revision, 0, True)
            assert record["id"] == implementation and record["profile_id"] == profile
            assert record["profile_import_id"] == source["id"]
            assert (record["catalog_id"], record["revision_id"], record["oscal_control_id"]) == (
                catalog,
                revision,
                "ac-1",
            )
            assert (record["description"], record["status"], record["evidence_references"]) == (
                "Kept",
                "implemented",
                ["evidence"],
            )
            assert (assignment["id"], assignment["user_id"], assignment["role"]) == (
                responsibility,
                user,
                "Owner",
            )
            connection.execute(
                text(
                    "INSERT INTO profile_imports "
                    "(id,tenant_id,profile_id,catalog_id,revision_id,position,active) "
                    "VALUES (:new_import,:tenant,:profile,:catalog,:revision,1,true)"
                ),
                {**args, "new_import": uuid4()},
            )
            with pytest.raises(RuntimeError, match="cannot be downgraded"):
                command.downgrade(config, "4d7e8f901abc")
        finally:
            transaction.rollback()
