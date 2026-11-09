import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4, uuid5

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.domain.catalogs.models import CatalogOriginType
from app.domain.errors import EntityNotFoundError
from app.persistence.identity import SQLIdentityRepository, SQLMembershipRepository
from app.persistence.models import (
    CatalogControlIndexRecord,
    CatalogGroupIndexRecord,
    CatalogRecord,
    CatalogRevisionRecord,
    OrganizationRecord,
    TenantMembershipRecord,
    UserIdentityRecord,
)

pytestmark = pytest.mark.integration
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "oscal_catalog.json"


def _catalog_document() -> dict:
    return json.loads(FIXTURE_PATH.read_text())


def test_repository_operations_and_tenant_isolation(grc_service, session_factory) -> None:
    tenant_a = grc_service.create_tenant("Tenant A", f"tenant-a-{uuid4().hex}")
    tenant_b = grc_service.create_tenant("Tenant B", f"tenant-b-{uuid4().hex}")
    assert tenant_a.id != tenant_b.id
    assert tenant_a.created_at.tzinfo is not None

    root = grc_service.create_organization(tenant_a.id, "Parent", "parent")
    child = grc_service.create_organization(
        tenant_a.id, "Child", "child", parent_organization_id=root.id
    )
    assert child.parent_organization_id == root.id
    with pytest.raises(EntityNotFoundError, match="parent not found"):
        grc_service.create_organization(
            tenant_b.id, "Foreign child", "foreign", parent_organization_id=root.id
        )

    catalog_a = grc_service.create_catalog(
        tenant_a.id,
        "Imported Example",
        CatalogOriginType.IMPORTED,
        source_uri="https://example.test/catalog.json",
        source_organization="Example publisher",
        license_identifier="CC0-1.0",
    )
    catalog_b = grc_service.create_catalog(tenant_a.id, "Custom Example", CatalogOriginType.CUSTOM)
    tenant_b_catalog = grc_service.create_catalog(
        tenant_b.id, "Other tenant", CatalogOriginType.CUSTOM
    )
    first_document = _catalog_document()
    revision_a1 = grc_service.create_draft_catalog_revision(
        tenant_a.id, catalog_a.id, first_document, source_version="1.0.0"
    )
    second_document = _catalog_document()
    second_document["catalog"]["metadata"]["title"] = "Example Security Catalog revised"
    revision_a2 = grc_service.create_draft_catalog_revision(
        tenant_a.id, catalog_a.id, second_document, source_version="1.1.0"
    )
    revision_b = grc_service.create_draft_catalog_revision(
        tenant_a.id, catalog_b.id, first_document
    )
    tenant_b_revision = grc_service.create_draft_catalog_revision(
        tenant_b.id, tenant_b_catalog.id, first_document
    )

    assert (revision_a1.revision_number, revision_a2.revision_number) == (1, 2)
    assert revision_a1.content == first_document
    assert revision_a1.content_sha256 == revision_b.content_sha256
    assert revision_a1.oscal_document_uuid == revision_b.oscal_document_uuid
    assert revision_a1.oscal_document_uuid == UUID(first_document["catalog"]["uuid"])
    assert revision_a1.content["catalog"]["metadata"]["title"] == "Example Security Catalog"
    assert grc_service.get_catalog_revision(tenant_a.id, revision_a1.id).content == first_document
    assert [item.id for item in grc_service.list_catalogs(tenant_a.id)] == [
        catalog_a.id,
        catalog_b.id,
    ]
    assert [
        item.oscal_control_id
        for item in grc_service.get_indexed_controls(tenant_a.id, revision_a1.id)
    ] == [
        "ac-1",
        "ac-1.1",
        "ac-2",
    ]
    with pytest.raises(EntityNotFoundError, match="not found"):
        grc_service.get_catalog_revision(tenant_a.id, tenant_b_revision.id)
    with pytest.raises(EntityNotFoundError, match="not found"):
        grc_service.get_indexed_controls(tenant_a.id, tenant_b_revision.id)

    with session_factory() as session:
        groups = list(
            session.scalars(
                select(CatalogGroupIndexRecord).where(
                    CatalogGroupIndexRecord.catalog_revision_id == revision_a1.id
                )
            )
        )
        controls = list(
            session.scalars(
                select(CatalogControlIndexRecord).where(
                    CatalogControlIndexRecord.catalog_revision_id == revision_a1.id
                )
            )
        )
        assert len(groups) == 2
        assert len(controls) == 3
        nested_group = next(group for group in groups if group.parent_group_id is not None)
        nested_control = next(
            control for control in controls if control.parent_control_id is not None
        )
        assert nested_group.structural_path == "/catalog/groups/0/groups/0"
        assert nested_group.id == uuid5(revision_a1.id, f"group:{nested_group.structural_path}")
        assert nested_control.oscal_control_id == "ac-1.1"
        assert nested_control.group_id == groups[0].id
        assert nested_control.id == uuid5(
            revision_a1.id, f"control:{nested_control.structural_path}"
        )
        assert (
            len(
                list(
                    session.scalars(
                        select(CatalogControlIndexRecord).where(
                            CatalogControlIndexRecord.catalog_revision_id == revision_a2.id
                        )
                    )
                )
            )
            == 3
        )


def test_invalid_references_and_failed_revision_write_roll_back(
    grc_service, session_factory
) -> None:
    tenant = grc_service.create_tenant("Rollback", f"rollback-{uuid4().hex}")
    unknown_tenant_id = uuid4()
    with pytest.raises(EntityNotFoundError, match="Tenant not found"):
        grc_service.create_catalog(unknown_tenant_id, "Orphan", CatalogOriginType.CUSTOM)
    with session_factory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(CatalogRecord)
                .where(CatalogRecord.tenant_id == unknown_tenant_id)
            )
            == 0
        )
    catalog = grc_service.create_catalog(tenant.id, "Rollback catalog", CatalogOriginType.CUSTOM)
    duplicate_controls = _catalog_document()
    control = duplicate_controls["catalog"]["groups"][0]["controls"][0]
    duplicate_controls["catalog"]["groups"][0]["controls"].append(dict(control))

    with pytest.raises(IntegrityError):
        grc_service.create_draft_catalog_revision(tenant.id, catalog.id, duplicate_controls)

    revision = grc_service.create_draft_catalog_revision(tenant.id, catalog.id, _catalog_document())
    assert revision.revision_number == 1
    with session_factory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(CatalogRevisionRecord)
                .where(CatalogRevisionRecord.catalog_id == catalog.id)
            )
            == 1
        )


def test_database_constraints_and_published_revision_immutability(
    grc_service, session_factory
) -> None:
    tenant_a = grc_service.create_tenant("Constraint A", f"constraint-a-{uuid4().hex}")
    tenant_b = grc_service.create_tenant("Constraint B", f"constraint-b-{uuid4().hex}")
    parent = grc_service.create_organization(tenant_b.id, "Foreign parent", "foreign-parent")
    with session_factory() as session:
        session.add(
            OrganizationRecord(
                id=uuid4(),
                tenant_id=tenant_a.id,
                parent_organization_id=parent.id,
                name="Invalid cross-tenant child",
                slug=f"invalid-{uuid4().hex}",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    with session_factory() as session:
        session.add(
            CatalogRecord(
                id=uuid4(),
                tenant_id=tenant_a.id,
                name="Invalid origin",
                origin_type="shared",
                source_uri=None,
                source_organization=None,
                license_identifier=None,
                description=None,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    catalog = grc_service.create_catalog(tenant_a.id, "Immutable", CatalogOriginType.CUSTOM)
    revision = grc_service.create_draft_catalog_revision(
        tenant_a.id, catalog.id, _catalog_document()
    )
    with session_factory() as session:
        session.execute(
            update(CatalogRevisionRecord)
            .where(CatalogRevisionRecord.id == revision.id)
            .values(
                lifecycle_status="published",
                published_at=datetime.now(UTC),
            )
        )
        session.commit()
        with pytest.raises(IntegrityError, match="Published catalog revisions are immutable"):
            session.execute(
                update(CatalogRevisionRecord)
                .where(CatalogRevisionRecord.id == revision.id)
                .values(content={"catalog": {}})
            )
            session.commit()
        session.rollback()


def test_alembic_upgrade_and_downgrade(db_engine, postgres_url: str) -> None:
    alembic_config = Config(str(Path(__file__).parents[3] / "alembic.ini"))
    alembic_config.attributes["database_url"] = postgres_url
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")

    with db_engine.connect() as connection:
        tables = set(connection.dialect.get_table_names(connection))
    assert {
        "tenants",
        "organizations",
        "catalogs",
        "catalog_revisions",
        "catalog_group_indexes",
        "catalog_control_indexes",
        "user_identities",
        "tenant_memberships",
    } <= tables


def test_identity_membership_constraints_and_tenant_isolation(grc_service, session_factory) -> None:
    tenant_a = grc_service.create_tenant("Identity tenant A", f"identity-a-{uuid4().hex}")
    tenant_b = grc_service.create_tenant("Identity tenant B", f"identity-b-{uuid4().hex}")
    with session_factory.begin() as session:
        identity = SQLIdentityRepository(session).get_or_create(
            issuer="https://issuer.example.test",
            subject="stable-subject",
            display_name="Identity",
            email=None,
        )
        membership = SQLMembershipRepository(session).assign(
            tenant_id=tenant_a.id,
            user_id=identity.id,
            role="viewer",
            status="active",
        )

    with session_factory() as session:
        assert (
            SQLMembershipRepository(session).get_for_tenant_and_user(tenant_a.id, identity.id)
            == membership
        )
        assert (
            SQLMembershipRepository(session).get_for_tenant_and_user(tenant_b.id, identity.id)
            is None
        )

    with session_factory() as session:
        session.add(
            UserIdentityRecord(
                id=uuid4(),
                issuer="https://issuer.example.test",
                subject="stable-subject",
                display_name=None,
                email=None,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    with session_factory() as session:
        session.add(
            TenantMembershipRecord(
                id=uuid4(),
                tenant_id=tenant_a.id,
                user_id=identity.id,
                role="viewer",
                status="active",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    with session_factory() as session:
        session.add(
            TenantMembershipRecord(
                id=uuid4(),
                tenant_id=tenant_b.id,
                user_id=identity.id,
                role="unknown-role",
                status="active",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_identity_and_membership_transaction_rolls_back(grc_service, session_factory) -> None:
    tenant = grc_service.create_tenant("Identity rollback", f"identity-rollback-{uuid4().hex}")
    with pytest.raises(RuntimeError, match="abort identity transaction"):
        with session_factory.begin() as session:
            identity = SQLIdentityRepository(session).get_or_create(
                issuer="https://issuer.example.test",
                subject=f"rollback-{uuid4().hex}",
                display_name=None,
                email=None,
            )
            SQLMembershipRepository(session).assign(
                tenant_id=tenant.id,
                user_id=identity.id,
                role="tenant_admin",
                status="active",
            )
            raise RuntimeError("abort identity transaction")

    with session_factory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(UserIdentityRecord)
                .where(UserIdentityRecord.subject.like("rollback-%"))
            )
            == 0
        )


def test_membership_foreign_keys_reject_unknown_tenant_and_identity(session_factory) -> None:
    now = datetime.now(UTC)
    identity_id, tenant_id = uuid4(), uuid4()
    with session_factory() as session:
        session.add(
            TenantMembershipRecord(
                id=uuid4(),
                tenant_id=tenant_id,
                user_id=identity_id,
                role="viewer",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_admin_bootstrap_is_idempotent_and_auditable(
    monkeypatch, caplog, grc_service, session_factory
) -> None:
    import logging

    from app import cli
    from app.config import Settings

    caplog.set_level(logging.INFO, logger=cli.__name__)
    issuer = "https://issuer.example.test"
    tenant = grc_service.create_tenant("Bootstrap", f"bootstrap-{uuid4().hex}")
    monkeypatch.setattr(
        cli,
        "get_settings",
        lambda: Settings(_env_file=None, oidc_issuer_url=issuer),
    )
    monkeypatch.setattr(cli, "create_session_factory", lambda: session_factory)

    first_identity_id, first_membership_id = cli._bootstrap_tenant_admin(
        issuer=issuer,
        subject="bootstrap-subject",
        tenant_id=tenant.id,
    )
    second_identity_id, second_membership_id = cli._bootstrap_tenant_admin(
        issuer=issuer,
        subject="bootstrap-subject",
        tenant_id=tenant.id,
    )

    assert (second_identity_id, second_membership_id) == (
        first_identity_id,
        first_membership_id,
    )
    with session_factory() as session:
        membership = session.scalar(
            select(TenantMembershipRecord).where(
                TenantMembershipRecord.tenant_id == tenant.id,
                TenantMembershipRecord.user_id == first_identity_id,
            )
        )
        identity_count = session.scalar(
            select(func.count())
            .select_from(UserIdentityRecord)
            .where(
                UserIdentityRecord.issuer == issuer,
                UserIdentityRecord.subject == "bootstrap-subject",
            )
        )
    assert membership is not None
    assert membership.role == "tenant_admin"
    assert membership.status == "active"
    assert identity_count == 1
    assert "tenant_admin_membership_bootstrapped" in caplog.text
