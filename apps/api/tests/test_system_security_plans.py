# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.application.component_definitions import (
    ComponentDefinitionService,
    ComponentInput,
    ComponentRequirementInput,
)
from app.application.implementations import ImplementationService
from app.application.system_security_plans import SystemSecurityPlanService
from app.domain.catalogs.models import CatalogOriginType
from app.domain.errors import EntityNotFoundError
from app.domain.implementations import (
    ImplementationInformation,
    ImplementationStatus,
    OscalImplementationStatus,
    Responsibility,
    ResponsibilityKind,
)
from app.persistence.identity import SQLIdentityRepository, SQLMembershipRepository
from app.persistence.models import ControlImplementationRecord

pytestmark = pytest.mark.integration
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "oscal_catalog.json"


def _actor(session_factory, tenant_id: UUID) -> UUID:
    with session_factory.begin() as session:
        identity = SQLIdentityRepository(session).get_or_create(
            issuer="https://issuer.example.test",
            subject=f"ssp-author-{uuid4()}",
            display_name="SSP Author",
            email=None,
        )
        SQLMembershipRepository(session).assign(
            tenant_id=tenant_id,
            user_id=identity.id,
            role="catalog_editor",
            status="active",
        )
        return identity.id


def test_system_ssp_shared_components_explicit_memberships_and_immutable_versions(
    grc_service, session_factory
) -> None:
    tenant = grc_service.create_tenant("SSP tenant", f"ssp-{uuid4().hex}")
    other_tenant = grc_service.create_tenant("Other tenant", f"ssp-other-{uuid4().hex}")
    actor = _actor(session_factory, tenant.id)
    catalog_one = grc_service.create_catalog(
        tenant.id, "Security baseline", CatalogOriginType.CUSTOM
    )
    catalog_two = grc_service.create_catalog(
        tenant.id, "Privacy baseline", CatalogOriginType.CUSTOM
    )
    catalog_document = json.loads(FIXTURE_PATH.read_text())
    revision_one = grc_service.create_draft_catalog_revision(
        tenant.id, catalog_one.id, catalog_document
    )
    revision_two = grc_service.create_draft_catalog_revision(
        tenant.id, catalog_two.id, catalog_document
    )
    implementations = ImplementationService(lambda: session_factory.begin())
    definitions = ComponentDefinitionService(lambda: session_factory.begin())
    ssp = SystemSecurityPlanService(lambda: session_factory.begin())

    legacy = implementations.create(
        tenant.id,
        actor,
        catalog_one.id,
        revision_one.id,
        "ac-1",
        None,
        None,
        ImplementationInformation(
            "The identity service enforces the approved policy.",
            ImplementationStatus.IN_PROGRESS,
            ["https://evidence.example.test/policy", "opaque-evidence-ref"],
            [Responsibility(ResponsibilityKind.ACCOUNTABLE, actor, "")],
            OscalImplementationStatus.IMPLEMENTED,
            None,
        ),
    )
    assert legacy.system_id is None
    assert legacy.system_component_id is None
    unassigned_legacy = implementations.create(
        tenant.id,
        actor,
        catalog_one.id,
        revision_one.id,
        "ac-2",
        None,
        None,
        ImplementationInformation(
            "Legacy record remains independent until explicitly associated.",
            ImplementationStatus.NOT_STARTED,
            [],
            [],
        ),
    )

    definition = definitions.create(
        tenant.id,
        actor,
        "Reusable identity measure",
        "service",
        "Reusable guidance; not evidence of deployment.",
        [
            ComponentRequirementInput(
                catalog_one.id,
                revision_one.id,
                "ac-1",
                "Apply approved identity policy.",
            )
        ],
    )
    source_component = definition.components[0]
    system = ssp.create_system(
        tenant.id,
        actor,
        name="Corporate Identity Management",
        organization_id=None,
        description="Identity services for employees.",
        system_boundary="The identity service and its managed infrastructure.",
        system_ids=[{"id": "identity.example", "identifier_type": "https://example.test/id-types"}],
        information_types=[
            {
                "title": "Employee identity data",
                "description": "Information used to authenticate employees.",
            }
        ],
        operational_status="operational",
        status_remarks=None,
        security_sensitivity_level=None,
    )
    concrete = ssp.create_component(
        tenant.id,
        actor,
        system["id"],
        component_type="service",
        title="Identity service",
        description="Production identity service deployment.",
        purpose="Authenticate employees.",
        status="operational",
        status_remarks=None,
    )
    adopted = ssp.adopt_component_definition(
        tenant.id,
        actor,
        system["id"],
        definition.id,
        source_component.id,
        title="Policy enforcement component",
        description="Deployed policy enforcement component.",
        purpose=None,
        status="operational",
        status_remarks=None,
    )
    assert adopted["source_component_uuid"] == source_component.oscal_uuid
    assert adopted["source_snapshot_id"] is not None

    plan_one = ssp.create_plan(
        tenant.id,
        actor,
        system["id"],
        catalog_id=catalog_one.id,
        revision_id=revision_one.id,
        title="Security SSP",
        control_implementation_description="Document each included contribution.",
    )
    plan_two = ssp.create_plan(
        tenant.id,
        actor,
        system["id"],
        catalog_id=catalog_two.id,
        revision_id=revision_two.id,
        title="Privacy SSP",
        control_implementation_description="Document each included contribution.",
    )
    assert plan_one["revision_id"] != plan_two["revision_id"]

    first_other_component = implementations.create(
        tenant.id,
        actor,
        catalog_one.id,
        revision_one.id,
        "ac-1",
        None,
        None,
        ImplementationInformation(
            "A second component contributes to the same requirement.",
            ImplementationStatus.NOT_STARTED,
            [],
            [],
            OscalImplementationStatus.PARTIAL,
            None,
        ),
    )
    second_requirement = implementations.create(
        tenant.id,
        actor,
        catalog_one.id,
        revision_one.id,
        "ac-2",
        None,
        None,
        ImplementationInformation(
            "The service applies the account-management procedure.",
            ImplementationStatus.IMPLEMENTED,
            [],
            [],
            OscalImplementationStatus.IMPLEMENTED,
            None,
        ),
    )
    different_baseline = implementations.create(
        tenant.id,
        actor,
        catalog_two.id,
        revision_two.id,
        "ac-1",
        None,
        None,
        ImplementationInformation(
            "The same deployed service supports the second baseline.",
            ImplementationStatus.NOT_STARTED,
            [],
            [],
            OscalImplementationStatus.PLANNED,
            "The remaining procedure is scheduled for the next release.",
        ),
    )

    include_one = ssp.associate_implementation(
        tenant.id,
        actor,
        plan_one["id"],
        legacy.id,
        concrete["id"],
        expected_version=plan_one["concurrency_version"],
    )
    plan_one["concurrency_version"] = include_one["concurrency_version"]
    include_two = ssp.associate_implementation(
        tenant.id,
        actor,
        plan_one["id"],
        first_other_component.id,
        adopted["id"],
        expected_version=plan_one["concurrency_version"],
    )
    plan_one["concurrency_version"] = include_two["concurrency_version"]
    include_three = ssp.associate_implementation(
        tenant.id,
        actor,
        plan_one["id"],
        second_requirement.id,
        concrete["id"],
        expected_version=plan_one["concurrency_version"],
    )
    plan_one["concurrency_version"] = include_three["concurrency_version"]
    include_four = ssp.associate_implementation(
        tenant.id,
        actor,
        plan_two["id"],
        different_baseline.id,
        concrete["id"],
        expected_version=plan_two["concurrency_version"],
    )
    plan_two["concurrency_version"] = include_four["concurrency_version"]
    assert ssp.get_system(tenant.id, system["id"])["id"] == system["id"]
    assert len(ssp.get_plan(tenant.id, plan_one["id"])["included_implementations"]) == 3
    assert len(ssp.get_plan(tenant.id, plan_two["id"])["included_implementations"]) == 1
    assert (
        len(
            {
                entry["system_component_id"]
                for entry in ssp.get_plan(plan_one["tenant_id"], plan_one["id"])[
                    "included_implementations"
                ]
                if entry["oscal_control_id"] == "ac-1"
            }
        )
        == 2
    )
    assert ssp.validate_plan(tenant.id, plan_one["id"])["valid"]

    version_one = ssp.create_version(
        tenant.id,
        actor,
        plan_one["id"],
        expected_version=plan_one["concurrency_version"],
    )
    plan_one["concurrency_version"] = version_one["concurrency_version"]
    assert version_one["created"]
    assert version_one["oscal_version"] == "1.2.1"
    exported_before = ssp.export_version(tenant.id, plan_one["id"], version_one["id"])
    assert exported_before["system-security-plan"]["metadata"]["oscal-version"] == "1.2.1"
    assert exported_before["system-security-plan"]["import-profile"]["href"].endswith(
        str(revision_one.id) + "/export"
    )
    requirement = exported_before["system-security-plan"]["control-implementation"][
        "implemented-requirements"
    ][0]
    assert len(requirement["by-components"]) == 2
    assert {item["implementation-status"]["state"] for item in requirement["by-components"]} == {
        "implemented",
        "partial",
    }
    assert any(
        link["href"] == "https://evidence.example.test/policy"
        for contribution in requirement["by-components"]
        for link in contribution.get("links", [])
    )
    assert any(
        diagnostic["code"] == "responsibilities_omitted"
        for diagnostic in version_one["diagnostics"]
    )
    assert any(
        diagnostic["code"] == "evidence_references_omitted"
        for diagnostic in version_one["diagnostics"]
    )

    updated_legacy = implementations.update(
        tenant.id,
        actor,
        legacy.id,
        ImplementationInformation(
            "The identity service enforces an updated approved policy.",
            ImplementationStatus.IMPLEMENTED,
            legacy.evidence_references,
            legacy.responsibilities,
            OscalImplementationStatus.IMPLEMENTED,
            None,
        ),
    )
    assert updated_legacy.id == legacy.id
    assert ssp.export_version(tenant.id, plan_one["id"], version_one["id"]) == exported_before
    version_two = ssp.create_version(
        tenant.id,
        actor,
        plan_one["id"],
        expected_version=plan_one["concurrency_version"],
    )
    plan_one["concurrency_version"] = version_two["concurrency_version"]
    assert version_two["created"]
    assert version_two["id"] != version_one["id"]
    assert version_two["oscal_document_uuid"] != version_one["oscal_document_uuid"]
    unchanged = ssp.create_version(
        tenant.id,
        actor,
        plan_one["id"],
        expected_version=plan_one["concurrency_version"],
    )
    assert unchanged["created"] is False
    assert unchanged["id"] == version_two["id"]
    assert ssp.export_version(tenant.id, plan_one["id"], version_one["id"]) == exported_before

    ssp.update_component(
        tenant.id,
        actor,
        system["id"],
        concrete["id"],
        title="Identity service",
        description="Updated production identity service deployment.",
        purpose="Authenticate employees.",
        status="operational",
        status_remarks=None,
    )
    assert ssp.export_version(tenant.id, plan_one["id"], version_one["id"]) == exported_before
    version_three = ssp.create_version(
        tenant.id,
        actor,
        plan_one["id"],
        expected_version=plan_one["concurrency_version"],
    )
    assert version_three["created"]

    historical_component = ssp.export_adopted_component(
        tenant.id, adopted["source_snapshot_id"], source_component.oscal_uuid
    )
    updated_definition = definitions.update(
        tenant.id,
        actor,
        definition.id,
        definition.concurrency_version,
        "Updated reusable identity measure",
        [
            ComponentInput(
                source_component.id,
                "service",
                "Revised source component",
                "Updated reusable guidance.",
                [
                    ComponentRequirementInput(
                        catalog_one.id,
                        revision_one.id,
                        "ac-1",
                        "Revised reusable policy guidance.",
                    )
                ],
            )
        ],
    )
    definitions.delete(
        tenant.id,
        definition.id,
        expected_version=updated_definition.concurrency_version,
    )
    assert (
        ssp.export_adopted_component(
            tenant.id, adopted["source_snapshot_id"], source_component.oscal_uuid
        )
        == historical_component
    )
    with session_factory.begin() as session:
        preserved = session.scalar(
            select(ControlImplementationRecord).where(
                ControlImplementationRecord.tenant_id == tenant.id,
                ControlImplementationRecord.id == legacy.id,
            )
        )
        assert preserved is not None
        assert preserved.system_id == system["id"]
        assert preserved.system_component_id == concrete["id"]
        unassigned = session.scalar(
            select(ControlImplementationRecord).where(
                ControlImplementationRecord.tenant_id == tenant.id,
                ControlImplementationRecord.id == unassigned_legacy.id,
            )
        )
        assert unassigned is not None
        assert unassigned.system_id is None
        assert unassigned.system_component_id is None
    with pytest.raises(EntityNotFoundError):
        ssp.get_system(other_tenant.id, system["id"])
