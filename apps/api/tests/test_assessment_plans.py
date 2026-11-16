from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.application.assessment_plans import AssessmentPlanService, InvalidAssessmentPlan
from app.application.implementations import ImplementationService
from app.application.system_security_plans import SystemSecurityPlanService
from app.domain.catalogs.models import CatalogOriginType
from app.domain.implementations import (
    ImplementationInformation,
    ImplementationStatus,
    OscalImplementationStatus,
)
from app.persistence.identity import SQLIdentityRepository, SQLMembershipRepository

pytestmark = pytest.mark.integration
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "oscal_catalog.json"


def _actor(session_factory, tenant_id: UUID) -> UUID:
    with session_factory.begin() as session:
        identity = SQLIdentityRepository(session).get_or_create(
            issuer="https://issuer.example.test",
            subject=f"ap-author-{uuid4()}",
            display_name="Assessment Plan Author",
            email=None,
        )
        SQLMembershipRepository(session).assign(
            tenant_id=tenant_id,
            user_id=identity.id,
            role="catalog_editor",
            status="active",
        )
        return identity.id


def _prepare_ssp_version(grc_service, session_factory) -> tuple[UUID, UUID, UUID, UUID, UUID]:
    tenant = grc_service.create_tenant("AP tenant", f"ap-{uuid4().hex}")
    actor = _actor(session_factory, tenant.id)
    catalog = grc_service.create_catalog(tenant.id, "Security baseline", CatalogOriginType.CUSTOM)
    catalog_document = json.loads(FIXTURE_PATH.read_text())
    revision = grc_service.create_draft_catalog_revision(tenant.id, catalog.id, catalog_document)

    ssp_service = SystemSecurityPlanService(lambda: session_factory.begin())
    implementations = ImplementationService(lambda: session_factory.begin())

    system = ssp_service.create_system(
        tenant.id,
        actor,
        name="Corporate Identity Management",
        organization_id=None,
        description="Identity services for employees.",
        system_boundary="Identity service and managed infrastructure.",
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
    component = ssp_service.create_component(
        tenant.id,
        actor,
        system["id"],
        component_type="service",
        title="Identity provider",
        description="Production identity service deployment.",
        purpose="Authenticate employees",
        status="operational",
        status_remarks=None,
    )
    plan = ssp_service.create_plan(
        tenant.id,
        actor,
        system["id"],
        catalog_id=catalog.id,
        revision_id=revision.id,
        title="Security SSP",
        control_implementation_description="Document requirement contributions.",
    )
    implementation = implementations.create(
        tenant.id,
        actor,
        catalog.id,
        revision.id,
        "ac-1",
        None,
        None,
        ImplementationInformation(
            "The identity provider enforces approved policy.",
            ImplementationStatus.IMPLEMENTED,
            [],
            [],
            OscalImplementationStatus.IMPLEMENTED,
            None,
        ),
    )
    ssp_service.associate_implementation(
        tenant.id,
        actor,
        plan["id"],
        implementation.id,
        component["id"],
    )
    version = ssp_service.create_version(tenant.id, actor, plan["id"])
    return tenant.id, actor, system["id"], version["id"], UUID(component["oscal_component_uuid"])


def test_assessment_plan_lifecycle_uses_pinned_ssp_snapshot(grc_service, session_factory) -> None:
    tenant_id, actor, system_id, ssp_version_id, subject_uuid = _prepare_ssp_version(
        grc_service, session_factory
    )
    service = AssessmentPlanService(lambda: session_factory.begin())

    plan = service.create_plan(
        tenant_id,
        actor,
        system_id,
        ssp_version_id=ssp_version_id,
        title="MFA Assessment",
        description="Assess MFA coverage for privileged access.",
    )

    updated = service.update_plan(
        tenant_id,
        actor,
        plan["id"],
        title="MFA Assessment",
        description="Assess MFA coverage for privileged access.",
        working_data={
            "control_ids": ["ac-1", "ac-2"],
            "source_objectives": [],
            "local_objectives": [
                {
                    "objective_id": "local-mfa-objective",
                    "control_id": "ac-1",
                    "description": "Determine whether MFA is enforced for privileged access.",
                    "methods": ["EXAMINE", "TEST"],
                }
            ],
            "subject_uuids": [str(subject_uuid)],
            "activities": [
                {
                    "title": "Review MFA configuration",
                    "description": "Review configuration and documentation.",
                    "methods": ["EXAMINE"],
                    "steps": [
                        {
                            "title": "Inspect policy",
                            "description": "Inspect MFA policy settings.",
                        }
                    ],
                    "control_ids": ["ac-1"],
                    "objective_ids": ["local-mfa-objective"],
                    "planned_evidence": "Configuration snapshot and policy reference.",
                },
                {
                    "title": "Test privileged sign-in",
                    "description": "Perform authentication test for privileged account.",
                    "methods": ["TEST"],
                    "steps": [],
                    "control_ids": ["ac-1"],
                    "objective_ids": ["local-mfa-objective"],
                    "planned_evidence": "Authentication logs.",
                },
            ],
            "tasks": [
                {
                    "title": "Execute MFA checks",
                    "description": "Coordinate assessment activities.",
                    "activity_ids": [],
                    "subject_uuids": [str(subject_uuid)],
                    "role_ids": ["assessor"],
                    "on_date": "2026-11-20T10:00:00+00:00",
                    "start": None,
                    "end": None,
                }
            ],
            "roles": [
                {
                    "role_id": "assessor",
                    "title": "Assessor",
                    "description": "Responsible for assessment execution planning.",
                    "party_uuids": [],
                }
            ],
            "parties": [
                {"party_type": "person", "name": "Alex Assessor"}
            ],
            "terms": "Production testing is restricted to approved windows.",
        },
    )

    assert updated["system_security_plan_version_id"] == ssp_version_id
    assert len(updated["activities"]) == 2
    validation = service.validate_plan(tenant_id, plan["id"])
    assert validation["valid"]

    first = service.create_version(tenant_id, actor, plan["id"])
    assert first["created"]
    assert first["oscal_version"] == "1.2.1"
    exported = service.export_version(tenant_id, plan["id"], first["id"])
    assert exported["assessment-plan"]["import-ssp"]["href"].endswith(
        f"/{ssp_version_id}/export"
    )

    unchanged = service.create_version(tenant_id, actor, plan["id"])
    assert unchanged["created"] is False
    assert unchanged["id"] == first["id"]


def test_assessment_plan_rejects_controls_or_subjects_outside_pinned_snapshot(
    grc_service, session_factory
) -> None:
    tenant_id, actor, system_id, ssp_version_id, _subject_uuid = _prepare_ssp_version(
        grc_service, session_factory
    )
    service = AssessmentPlanService(lambda: session_factory.begin())

    plan = service.create_plan(
        tenant_id,
        actor,
        system_id,
        ssp_version_id=ssp_version_id,
        title="Invalid AP",
        description=None,
    )

    with pytest.raises(InvalidAssessmentPlan):
        service.update_plan(
            tenant_id,
            actor,
            plan["id"],
            title="Invalid AP",
            description=None,
            working_data={
                "control_ids": ["not-a-real-control"],
                "source_objectives": [],
                "local_objectives": [],
                "subject_uuids": [str(uuid4())],
                "activities": [],
                "tasks": [],
                "roles": [],
                "parties": [],
                "terms": None,
            },
        )


