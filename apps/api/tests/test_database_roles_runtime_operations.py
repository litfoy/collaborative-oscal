# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

"""Representative existing workflows executed with the ``oscal_runtime`` credential.

Fixture setup that is administrative in ADR 0029 (tenant and membership creation) uses the
owner connection. Everything else runs through the unchanged application services on the
runtime engine, exercising reads, RETURNING/upserts, row locks, FK validation, revision-lock
and immutability triggers and immutable version inserts.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.application.catalog_import import CatalogImportService
from app.application.component_definitions import (
    ComponentDefinitionService,
    ComponentRequirementInput,
)
from app.application.implementations import ImplementationService
from app.application.services import GrcService
from app.application.system_security_plans import SystemSecurityPlanService
from app.domain.catalogs.models import CatalogOriginType
from app.domain.implementations import (
    ImplementationInformation,
    ImplementationStatus,
    OscalImplementationStatus,
)
from app.persistence.database_roles import RUNTIME_ROLE
from app.persistence.identity import SQLIdentityRepository, SQLMembershipRepository
from app.persistence.repositories import SQLAlchemyUnitOfWork

pytestmark = [pytest.mark.integration, pytest.mark.database_roles]
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "oscal_catalog.json"


def _grc(factory: sessionmaker[Session]) -> GrcService:
    return GrcService(lambda: SQLAlchemyUnitOfWork(factory))


def _runtime_actor(
    runtime_session_factory: sessionmaker[Session],
    owner_session_factory: sessionmaker[Session],
    tenant_id: UUID,
) -> UUID:
    subject = f"runtime-role-{uuid4()}"
    with runtime_session_factory.begin() as session:
        assert session.execute(text("SELECT current_user")).scalar_one() == RUNTIME_ROLE
        identity = SQLIdentityRepository(session).get_or_create(
            issuer="https://issuer.example.test",
            subject=subject,
            display_name="Runtime Author",
            email=None,
        )
    with runtime_session_factory.begin() as session:
        updated = SQLIdentityRepository(session).get_or_create(
            issuer="https://issuer.example.test",
            subject=subject,
            display_name="Runtime Author (renamed)",
            email="author@example.test",
        )
    assert updated.id == identity.id and updated.display_name == "Runtime Author (renamed)"
    with owner_session_factory.begin() as session:
        SQLMembershipRepository(session).assign(
            tenant_id=tenant_id, user_id=identity.id, role="catalog_editor", status="active"
        )
    return identity.id


def test_runtime_rejects_administrative_service_paths(
    runtime_session_factory: sessionmaker[Session],
) -> None:
    with pytest.raises(Exception) as raised:
        _grc(runtime_session_factory).create_tenant("Denied", f"denied-{uuid4().hex}")
    assert getattr(getattr(raised.value, "orig", None), "sqlstate", None) == "42501"


def test_runtime_executes_catalog_component_and_ssp_publication_workflow(
    runtime_session_factory: sessionmaker[Session],
    owner_session_factory: sessionmaker[Session],
    owner_cleanup,
) -> None:
    tenant = _grc(owner_session_factory).create_tenant("Runtime tenant", f"rt-{uuid4().hex}")
    actor = _runtime_actor(runtime_session_factory, owner_session_factory, tenant.id)
    grc = _grc(runtime_session_factory)

    imported = CatalogImportService(
        lambda: SQLAlchemyUnitOfWork(runtime_session_factory)
    ).import_catalog(tenant.id, FIXTURE_PATH.read_bytes())
    assert imported.revision is not None

    catalog = grc.create_catalog(tenant.id, "Runtime baseline", CatalogOriginType.CUSTOM)
    revision = grc.create_draft_catalog_revision(
        tenant.id, catalog.id, json.loads(FIXTURE_PATH.read_text())
    )
    implementations = ImplementationService(lambda: runtime_session_factory.begin())
    definitions = ComponentDefinitionService(lambda: runtime_session_factory.begin())
    ssp = SystemSecurityPlanService(lambda: runtime_session_factory.begin())

    implementation = implementations.create(
        tenant.id,
        actor,
        catalog.id,
        revision.id,
        "ac-1",
        None,
        None,
        ImplementationInformation(
            "The identity service enforces the approved policy.",
            ImplementationStatus.IN_PROGRESS,
            [],
            [],
            OscalImplementationStatus.IMPLEMENTED,
            None,
        ),
    )
    definition = definitions.create(
        tenant.id,
        actor,
        "Reusable identity measure",
        "service",
        "Reusable guidance.",
        [ComponentRequirementInput(catalog.id, revision.id, "ac-1", "Apply policy.")],
    )
    system = ssp.create_system(
        tenant.id,
        actor,
        name="Runtime Identity System",
        organization_id=None,
        description="Identity services.",
        system_boundary="The identity service.",
        system_ids=[{"id": "rt.example", "identifier_type": "https://example.test/id-types"}],
        information_types=[{"title": "Identity data", "description": "Authentication data."}],
        operational_status="operational",
        status_remarks=None,
        security_sensitivity_level=None,
    )
    component = ssp.create_component(
        tenant.id,
        actor,
        system["id"],
        component_type="service",
        title="Identity service",
        description="Production deployment.",
        purpose="Authenticate employees.",
        status="operational",
        status_remarks=None,
    )
    adopted = ssp.adopt_component_definition(
        tenant.id,
        actor,
        system["id"],
        definition.id,
        definition.components[0].id,
        title="Policy enforcement",
        description="Adopted component.",
        purpose=None,
        status="operational",
        status_remarks=None,
    )
    assert adopted["source_snapshot_id"] is not None
    plan = ssp.create_plan(
        tenant.id,
        actor,
        system["id"],
        catalog_id=catalog.id,
        revision_id=revision.id,
        title="Runtime SSP",
        control_implementation_description="Included contributions.",
    )
    included = ssp.associate_implementation(
        tenant.id,
        actor,
        plan["id"],
        implementation.id,
        component["id"],
        expected_version=plan["concurrency_version"],
        expected_implementation_version=implementation.concurrency_version,
    )
    assert ssp.validate_plan(tenant.id, plan["id"])["valid"]
    version = ssp.create_version(
        tenant.id, actor, plan["id"], expected_version=included["concurrency_version"]
    )
    assert version["created"]
    repeated = ssp.create_version(
        tenant.id, actor, plan["id"], expected_version=version["concurrency_version"]
    )
    assert not repeated["created"] and repeated["id"] == version["id"]
    exported = ssp.export_version(tenant.id, plan["id"], version["id"])
    assert exported["system-security-plan"]["metadata"]["oscal-version"] == "1.2.1"
    assert runtime_session_factory.kw["bind"].pool.checkedout() == 0
