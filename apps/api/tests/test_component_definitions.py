from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from collaborative_oscal_oscal.component_definition import validate_component_definition_document
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.application.component_definitions import (
    ComponentDefinitionService,
    ComponentInput,
    ComponentRequirementInput,
    InvalidComponentDefinition,
)
from app.application.implementations import ImplementationService
from app.domain.errors import EntityNotFoundError
from app.domain.identity.models import UserIdentity
from app.domain.implementations import ImplementationInformation, ImplementationStatus
from app.persistence.identity import SQLIdentityRepository, SQLMembershipRepository
from app.persistence.models import (
    CatalogRevisionRecord,
    ComponentDefinitionComponentRecord,
    ComponentDefinitionRecord,
    ComponentDefinitionSourceRecord,
    ControlImplementationRecord,
)

pytestmark = pytest.mark.integration
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "oscal_catalog.json"


def _catalog_document() -> dict:
    return json.loads(FIXTURE_PATH.read_text())


def _actor(session_factory, tenant_id: UUID) -> UserIdentity:
    with session_factory.begin() as session:
        identity = SQLIdentityRepository(session).get_or_create(
            issuer="https://issuer.example.test",
            subject=f"component-author-{uuid4()}",
            display_name="Component Author",
            email=None,
        )
        SQLMembershipRepository(session).assign(
            tenant_id=tenant_id,
            user_id=identity.id,
            role="catalog_editor",
            status="active",
        )
    return identity


def test_component_definition_sources_identity_and_deletion(
    grc_service, session_factory
) -> None:
    from app.domain.catalogs.models import CatalogOriginType

    tenant = grc_service.create_tenant("Component tenant", f"component-{uuid4().hex}")
    other_tenant = grc_service.create_tenant("Other tenant", f"other-{uuid4().hex}")
    actor = _actor(session_factory, tenant.id)
    catalogs = [
        grc_service.create_catalog(tenant.id, name, CatalogOriginType.CUSTOM)
        for name in ("Security", "Privacy", "Implementation")
    ]
    other_catalog = grc_service.create_catalog(
        other_tenant.id, "Other tenant catalog", CatalogOriginType.CUSTOM
    )
    revisions = [
        grc_service.create_draft_catalog_revision(tenant.id, catalog.id, _catalog_document())
        for catalog in catalogs
    ]
    other_revision = grc_service.create_draft_catalog_revision(
        other_tenant.id, other_catalog.id, _catalog_document()
    )
    service = ComponentDefinitionService(lambda: session_factory.begin())

    implementation = ImplementationService(lambda: session_factory.begin()).create(
        tenant.id,
        actor.id,
        catalogs[2].id,
        revisions[2].id,
        "ac-1",
        None,
        None,
        ImplementationInformation(
            "Existing operational implementation.",
            ImplementationStatus.IN_PROGRESS,
            ["evidence-ref"],
            [],
        ),
    )
    created = service.create(
        tenant.id,
        actor.id,
        "Multifactor authentication",
        "policy",
        "A reusable security and privacy measure.",
        [
            ComponentRequirementInput(
                catalogs[0].id,
                revisions[0].id,
                "ac-1",
                "Require MFA for privileged access.",
            ),
            ComponentRequirementInput(
                catalogs[0].id,
                revisions[0].id,
                "ac-2",
                "Require MFA when managing privileged accounts.",
            ),
            ComponentRequirementInput(
                catalogs[1].id,
                revisions[1].id,
                "ac-1",
                "Require MFA before processing sensitive information.",
            ),
        ],
    )

    loaded = service.get(tenant.id, created.id)
    assert loaded.components[0].id == created.components[0].id
    assert loaded.components[0].oscal_uuid == created.components[0].oscal_uuid
    assert {
        (item.catalog_id, item.revision_id, item.control_id)
        for item in loaded.components[0].requirements
    } == {
        (catalogs[0].id, revisions[0].id, "ac-1"),
        (catalogs[0].id, revisions[0].id, "ac-2"),
        (catalogs[1].id, revisions[1].id, "ac-1"),
    }
    with pytest.raises(EntityNotFoundError):
        service.get(other_tenant.id, created.id)
    with pytest.raises(EntityNotFoundError):
        service.create(
            tenant.id,
            actor.id,
            "Unauthorized source",
            "policy",
            "",
            [ComponentRequirementInput(other_catalog.id, other_revision.id, "ac-1", "Text")],
        )
    with pytest.raises(InvalidComponentDefinition, match="do not exist"):
        service.create(
            tenant.id,
            actor.id,
            "Invalid control",
            "policy",
            "",
            [ComponentRequirementInput(catalogs[0].id, revisions[0].id, "unknown", "Text")],
        )

    before = service.export(tenant.id, created.id)["component-definition"]
    exported_again = service.export(tenant.id, created.id)["component-definition"]
    assert exported_again["uuid"] == before["uuid"]
    assert exported_again["metadata"]["last-modified"] == before["metadata"]["last-modified"]
    before_sets = {
        (source["source"], req["control-id"]): (
            source["uuid"],
            req["uuid"],
        )
        for source in before["components"][0]["control-implementations"]
        for req in source["implemented-requirements"]
    }
    updated = service.update(
        tenant.id,
        actor.id,
        created.id,
        "MFA reusable measure",
        [
            ComponentInput(
                created.components[0].id,
                "policy",
                "Multifactor authentication",
                "Updated reusable guidance.",
                [
                    ComponentRequirementInput(
                        catalogs[0].id,
                        revisions[0].id,
                        "ac-1",
                        "Require MFA for privileged access and record exceptions.",
                    ),
                    ComponentRequirementInput(
                        catalogs[0].id,
                        revisions[0].id,
                        "ac-2",
                        "Require MFA when managing privileged accounts.",
                    ),
                    ComponentRequirementInput(
                        catalogs[1].id,
                        revisions[1].id,
                        "ac-1",
                        "Require MFA before processing sensitive information.",
                    ),
                ],
            ),
            ComponentInput(None, "process-procedure", "Enrollment", "Enrollment guidance.", []),
        ],
    )
    assert updated.id == created.id
    assert updated.components[0].id == created.components[0].id
    assert updated.components[0].oscal_uuid == created.components[0].oscal_uuid
    after = service.export(tenant.id, created.id)["component-definition"]
    assert after["uuid"] != before["uuid"]
    assert after["metadata"]["last-modified"] != before["metadata"]["last-modified"]
    after_sets = {
        (source["source"], req["control-id"]): (
            source["uuid"],
            req["uuid"],
        )
        for source in after["components"][0]["control-implementations"]
        for req in source["implemented-requirements"]
    }
    assert after_sets == before_sets
    validate_component_definition_document(service.export(tenant.id, created.id))

    with session_factory() as session:
        source_count = session.scalar(
            select(func.count()).select_from(ComponentDefinitionSourceRecord).where(
                ComponentDefinitionSourceRecord.document_id == created.id
            )
        )
        implementation_count = session.scalar(
            select(func.count())
            .select_from(ControlImplementationRecord)
            .where(ControlImplementationRecord.id == implementation.id)
        )
    assert source_count == 3
    assert implementation_count == 1

    with session_factory() as session:
        with pytest.raises(IntegrityError, match="Component Definitions are immutable"):
            session.execute(
                update(CatalogRevisionRecord)
                .where(CatalogRevisionRecord.id == revisions[0].id)
                .values(content={"catalog": {}})
            )
            session.commit()
        session.rollback()

    service.delete_component(tenant.id, actor.id, created.id, created.components[0].id)
    remaining = service.get(tenant.id, created.id)
    assert len(remaining.components) == 1
    service.delete_component(tenant.id, actor.id, created.id, remaining.components[0].id)
    with pytest.raises(EntityNotFoundError):
        service.get(tenant.id, created.id)
    still_present = ImplementationService(lambda: session_factory.begin()).get(
        tenant.id, implementation.id
    )
    assert still_present.description == "Existing operational implementation."

    with session_factory() as session:
        assert session.scalar(
            select(func.count()).select_from(ComponentDefinitionRecord).where(
                ComponentDefinitionRecord.id == created.id
            )
        ) == 0
        assert session.scalar(
            select(func.count()).select_from(ComponentDefinitionComponentRecord).where(
                ComponentDefinitionComponentRecord.document_id == created.id
            )
        ) == 0
        assert session.scalar(
            select(func.count()).select_from(ComponentDefinitionSourceRecord).where(
                ComponentDefinitionSourceRecord.document_id == created.id
            )
        ) == 0
        session.execute(
            update(CatalogRevisionRecord)
            .where(CatalogRevisionRecord.id == revisions[0].id)
            .values(content={"catalog": {"after-delete": True}})
        )
        session.commit()
