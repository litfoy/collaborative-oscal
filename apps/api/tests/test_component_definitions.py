# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, tzinfo
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from collaborative_oscal_oscal.component_definition import validate_component_definition_document
from psycopg.errors import RaiseException
from sqlalchemy import func, select, update
from sqlalchemy.exc import ProgrammingError

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
        with pytest.raises(
            ProgrammingError,
            match="Catalog revisions referenced by Component Definitions are immutable",
        ) as rejected:
            session.execute(
                update(CatalogRevisionRecord)
                .where(CatalogRevisionRecord.id == revisions[0].id)
                .values(content={"catalog": {}})
            )
            session.commit()
        session.rollback()
        assert isinstance(rejected.value.orig, RaiseException)
        assert rejected.value.orig.sqlstate == "P0001"
        assert rejected.value.orig.diag.message_primary == (
            "Catalog revisions referenced by Component Definitions are immutable"
        )
        context = rejected.value.orig.diag.context
        assert context is not None
        assert "protect_component_definition_source_revision()" in context

    with session_factory() as session:
        stored = session.get(CatalogRevisionRecord, revisions[0].id)
        assert stored is not None
        assert stored.content == revisions[0].content
        assert stored.content_sha256 == revisions[0].content_sha256
        assert stored.updated_at == revisions[0].updated_at
    assert service.export(tenant.id, created.id)["component-definition"] == after

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


def test_same_second_component_changes_preserve_document_lifecycle(
    monkeypatch, grc_service, session_factory
) -> None:
    from app.application import component_definitions

    now = datetime(2026, 11, 16, 12, 0, 0, 500000, tzinfo=UTC)

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> datetime:
            return now.astimezone(tz)

    monkeypatch.setattr(component_definitions, "datetime", FrozenDatetime)
    tenant = grc_service.create_tenant("Lifecycle", f"lifecycle-{uuid4().hex}")
    actor = _actor(session_factory, tenant.id)
    service = ComponentDefinitionService(lambda: session_factory.begin())
    created = service.create(tenant.id, actor.id, "Policy", "policy", "Guidance", [])
    original = service.export(tenant.id, created.id)
    inputs = [
        ComponentInput(created.components[0].id, "policy", "Policy", "Guidance", []),
        ComponentInput(None, "process-procedure", "Enrollment", "Process", []),
    ]
    updated = service.update(tenant.id, actor.id, created.id, "Policies", inputs)
    changed = service.export(tenant.id, created.id)
    inputs[1] = ComponentInput(
        updated.components[1].id, "process-procedure", "Enrollment", "Process", []
    )
    service.update(tenant.id, actor.id, created.id, "Policies", inputs)
    assert service.export(tenant.id, created.id) == changed

    service.delete_component(tenant.id, actor.id, created.id, updated.components[1].id)
    deleted = service.export(tenant.id, created.id)
    documents = [original, changed, deleted]
    assert len({doc["component-definition"]["uuid"] for doc in documents}) == 3
    for offset, doc in enumerate(documents):
        body = doc["component-definition"]
        assert body["metadata"]["version"] == f"1.0.{offset}"
        modified = datetime.fromisoformat(body["metadata"]["last-modified"])
        assert modified == now.replace(microsecond=0) + timedelta(seconds=offset)
        assert body["components"][0]["uuid"] == str(created.components[0].oscal_uuid)
        assert body["metadata"]["oscal-version"] == "1.2.1"
        validate_component_definition_document(doc)
    assert service.export(tenant.id, created.id) == deleted
