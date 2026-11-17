from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.application.assessment_plans import AssessmentPlanService
from app.application.assessment_results import (
    AssessmentResultService,
    InvalidAssessmentResult,
)
from app.application.implementations import ImplementationService
from app.application.system_security_plans import SystemSecurityPlanService
from app.domain.catalogs.models import CatalogOriginType
from app.domain.errors import EntityNotFoundError
from app.domain.implementations import (
    ImplementationInformation,
    ImplementationStatus,
    OscalImplementationStatus,
)
from app.persistence.identity import SQLIdentityRepository, SQLMembershipRepository
from app.persistence.models import CatalogControlIndexRecord

pytestmark = pytest.mark.integration
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "oscal_catalog.json"


def _actor(session_factory, tenant_id: UUID) -> UUID:
    with session_factory.begin() as session:
        identity = SQLIdentityRepository(session).get_or_create(
            issuer="https://issuer.example.test",
            subject=f"ar-author-{uuid4()}",
            display_name="Assessment Results Author",
            email=None,
        )
        SQLMembershipRepository(session).assign(
            tenant_id=tenant_id,
            user_id=identity.id,
            role="catalog_editor",
            status="active",
        )
        return identity.id


def _prepare_plan_version(grc_service, session_factory):
    tenant = grc_service.create_tenant("AR tenant", f"ar-{uuid4().hex}")
    actor = _actor(session_factory, tenant.id)
    catalog = grc_service.create_catalog(tenant.id, "Security baseline", CatalogOriginType.CUSTOM)
    document = json.loads(FIXTURE_PATH.read_text())
    revision = grc_service.create_draft_catalog_revision(tenant.id, catalog.id, document)

    with session_factory.begin() as session:
        controls = session.scalars(
            select(CatalogControlIndexRecord.oscal_control_id)
            .where(
                CatalogControlIndexRecord.tenant_id == tenant.id,
                CatalogControlIndexRecord.catalog_revision_id == revision.id,
            )
            .order_by(CatalogControlIndexRecord.oscal_control_id)
        ).all()

    ssp_service = SystemSecurityPlanService(lambda: session_factory.begin())
    implementations = ImplementationService(lambda: session_factory.begin())
    ap_service = AssessmentPlanService(lambda: session_factory.begin())

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
    ssp = ssp_service.create_plan(
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
        controls[0],
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
        ssp["id"],
        implementation.id,
        component["id"],
    )
    ssp_version = ssp_service.create_version(tenant.id, actor, ssp["id"])

    plan = ap_service.create_plan(
        tenant.id,
        actor,
        system["id"],
        ssp_version_id=ssp_version["id"],
        title="MFA Assessment",
        description="Assess MFA coverage.",
    )
    subject_uuid = component["oscal_component_uuid"]
    ap_service.update_plan(
        tenant.id,
        actor,
        plan["id"],
        title=plan["title"],
        description=plan["description"],
        working_data={
            "control_ids": [controls[0]],
            "source_objectives": [],
            "local_objectives": [
                {
                    "objective_id": "local-mfa-objective",
                    "control_id": controls[0],
                    "description": "Determine whether MFA is enforced for privileged access.",
                    "methods": ["EXAMINE", "TEST"],
                }
            ],
            "subject_uuids": [str(subject_uuid)],
            "activities": [],
            "tasks": [],
            "roles": [],
            "parties": [],
            "terms": None,
        },
    )
    plan_version = ap_service.create_version(tenant.id, actor, plan["id"])
    return tenant.id, actor, system["id"], plan, plan_version, controls[0], UUID(str(subject_uuid))


def _prepare_plan_scope_context(
    grc_service,
    session_factory,
    *,
    selected_control_count: int = 2,
    selected_subject_indexes: tuple[int, ...] = (0,),
    local_objectives: list[dict[str, object]] | None = None,
    catalog_document: dict | None = None,
) -> dict[str, object]:
    tenant = grc_service.create_tenant("AR scope tenant", f"ar-scope-{uuid4().hex}")
    actor = _actor(session_factory, tenant.id)
    catalog = grc_service.create_catalog(tenant.id, "Security baseline", CatalogOriginType.CUSTOM)
    revision = grc_service.create_draft_catalog_revision(
        tenant.id,
        catalog.id,
        catalog_document or json.loads(FIXTURE_PATH.read_text()),
    )

    with session_factory.begin() as session:
        controls = session.scalars(
            select(CatalogControlIndexRecord.oscal_control_id)
            .where(
                CatalogControlIndexRecord.tenant_id == tenant.id,
                CatalogControlIndexRecord.catalog_revision_id == revision.id,
            )
            .order_by(CatalogControlIndexRecord.oscal_control_id)
        ).all()

    ssp_service = SystemSecurityPlanService(lambda: session_factory.begin())
    implementations = ImplementationService(lambda: session_factory.begin())
    ap_service = AssessmentPlanService(lambda: session_factory.begin())
    ar_service = AssessmentResultService(lambda: session_factory.begin())

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
    component_a = ssp_service.create_component(
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
    component_b = ssp_service.create_component(
        tenant.id,
        actor,
        system["id"],
        component_type="service",
        title="Federation gateway",
        description="Federation service deployment.",
        purpose="Support partner identity federation",
        status="operational",
        status_remarks=None,
    )
    ssp = ssp_service.create_plan(
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
        controls[0],
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
        ssp["id"],
        implementation.id,
        component_a["id"],
    )
    ssp_version = ssp_service.create_version(tenant.id, actor, ssp["id"])

    component_uuids = [
        str(component_a["oscal_component_uuid"]),
        str(component_b["oscal_component_uuid"]),
    ]
    selected_subjects = [
        component_uuids[index]
        for index in selected_subject_indexes
        if 0 <= index < len(component_uuids)
    ]

    plan = ap_service.create_plan(
        tenant.id,
        actor,
        system["id"],
        ssp_version_id=ssp_version["id"],
        title="Scoped AP",
        description="Scope for AR hardening tests.",
    )
    ap_service.update_plan(
        tenant.id,
        actor,
        plan["id"],
        title=plan["title"],
        description=plan["description"],
        working_data={
            "control_ids": controls[:selected_control_count],
            "source_objectives": [],
            "local_objectives": local_objectives or [],
            "subject_uuids": selected_subjects,
            "activities": [],
            "tasks": [],
            "roles": [],
            "parties": [],
            "terms": None,
        },
    )
    plan_version = ap_service.create_version(tenant.id, actor, plan["id"])
    return {
        "tenant_id": tenant.id,
        "actor": actor,
        "system_id": system["id"],
        "plan": plan,
        "plan_version": plan_version,
        "controls": controls,
        "subjects": component_uuids,
        "ap_service": ap_service,
        "ar_service": ar_service,
    }


def test_assessment_result_lifecycle_uses_pinned_assessment_plan_context(
    grc_service, session_factory
) -> None:
    (
        tenant_id,
        actor,
        system_id,
        plan,
        plan_version,
        control_id,
        subject_uuid,
    ) = _prepare_plan_version(grc_service, session_factory)
    service = AssessmentResultService(lambda: session_factory.begin())

    result = service.create_result(
        tenant_id,
        actor,
        system_id,
        assessment_plan_id=plan["id"],
        assessment_plan_version_id=plan_version["id"],
        title="MFA Results",
        description="Execution outcome.",
    )

    updated = service.update_result(
        tenant_id,
        actor,
        result["id"],
        title="MFA Results",
        description="Execution outcome.",
        working_data={
            "reviewed_control_ids": [control_id],
            "start": "2026-11-20T00:00:00+00:00",
            "end": "2026-11-20T01:00:00+00:00",
            "observations": [
                {
                    "title": "MFA challenge observed",
                    "description": "MFA challenge is enforced for privileged login.",
                    "methods": ["EXAMINE"],
                    "collected_at": "2026-11-20T00:30:00+00:00",
                    "subject_uuids": [str(subject_uuid)],
                    "evidence": [
                        {
                            "title": "Authentication logs",
                            "description": "Export from production login audit trail.",
                            "href": "https://example.test/evidence/mfa-logs",
                        }
                    ],
                }
            ],
            "findings": [
                {
                    "title": "AC-1 statement coverage",
                    "description": "Statement is implemented and evidenced.",
                    "target_type": "objective-id",
                    "target_id": "local-mfa-objective",
                    "status": "satisfied",
                    "related_observation_ids": [],
                }
            ],
        },
    )
    observation_id = updated["observations"][0]["id"]

    updated = service.update_result(
        tenant_id,
        actor,
        result["id"],
        title="MFA Results",
        description="Execution outcome.",
        working_data={
            "reviewed_control_ids": [control_id],
            "start": "2026-11-20T00:00:00+00:00",
            "end": "2026-11-20T01:00:00+00:00",
            "observations": updated["observations"],
            "findings": [
                {
                    "title": "AC-1 statement coverage",
                    "description": "Statement is implemented and evidenced.",
                    "target_type": "objective-id",
                    "target_id": "local-mfa-objective",
                    "status": "satisfied",
                    "related_observation_ids": [str(observation_id)],
                }
            ],
        },
    )

    validation = service.validate_result(tenant_id, result["id"])
    assert validation["valid"]

    version = service.create_version(tenant_id, actor, result["id"])
    assert version["created"] is True
    assert version["oscal_version"] == "1.2.1"
    exported = service.export_version(tenant_id, result["id"], version["id"])
    assert exported["assessment-results"]["import-ap"]["href"].endswith(
        f"/{plan_version['id']}/export"
    )

    unchanged = service.create_version(tenant_id, actor, result["id"])
    assert unchanged["created"] is False
    assert unchanged["id"] == version["id"]


def test_assessment_result_rejects_unknown_statement_and_subject(
    grc_service, session_factory
) -> None:
    (
        tenant_id,
        actor,
        system_id,
        plan,
        plan_version,
        control_id,
        _subject_uuid,
    ) = _prepare_plan_version(grc_service, session_factory)
    service = AssessmentResultService(lambda: session_factory.begin())

    result = service.create_result(
        tenant_id,
        actor,
        system_id,
        assessment_plan_id=plan["id"],
        assessment_plan_version_id=plan_version["id"],
        title="Invalid AR",
        description=None,
    )

    with pytest.raises(InvalidAssessmentResult):
        service.update_result(
            tenant_id,
            actor,
            result["id"],
            title="Invalid AR",
            description=None,
            working_data={
                "reviewed_control_ids": [control_id],
                "start": None,
                "end": None,
                "observations": [
                    {
                        "title": "Observation",
                        "description": "desc",
                        "methods": ["SCAN"],
                        "collected_at": "2026-11-20T00:30:00+00:00",
                        "subject_uuids": [str(uuid4())],
                        "evidence": [],
                    }
                ],
                "findings": [
                    {
                        "title": "Bad target",
                        "description": "desc",
                        "target_type": "statement-id",
                        "target_id": "does-not-exist",
                        "status": "satisfied",
                        "related_observation_ids": [],
                    }
                ],
            },
        )


def test_assessment_result_rejects_cross_tenant_assessment_plan_reference(
    grc_service, session_factory
) -> None:
    (
        tenant_a,
        _actor_a,
        _system_a,
        plan_a,
        plan_version_a,
        _control_a,
        _subject_a,
    ) = _prepare_plan_version(grc_service, session_factory)
    (
        tenant_b,
        actor_b,
        system_b,
        _plan_b,
        _plan_version_b,
        _control_b,
        _subject_b,
    ) = _prepare_plan_version(grc_service, session_factory)
    service = AssessmentResultService(lambda: session_factory.begin())

    with pytest.raises(EntityNotFoundError, match="Assessment Plan not found"):
        service.create_result(
            tenant_b,
            actor_b,
            system_b,
            assessment_plan_id=plan_a["id"],
            assessment_plan_version_id=plan_version_a["id"],
            title="Cross-tenant AR",
            description=None,
        )


def test_assessment_result_version_creation_is_stable_under_concurrency(
    grc_service, session_factory
) -> None:
    (
        tenant_id,
        actor,
        system_id,
        plan,
        plan_version,
        control_id,
        subject_uuid,
    ) = _prepare_plan_version(grc_service, session_factory)
    service = AssessmentResultService(lambda: session_factory.begin())
    result = service.create_result(
        tenant_id,
        actor,
        system_id,
        assessment_plan_id=plan["id"],
        assessment_plan_version_id=plan_version["id"],
        title="Concurrent version AR",
        description=None,
    )
    updated = service.update_result(
        tenant_id,
        actor,
        result["id"],
        title="Concurrent version AR",
        description=None,
        working_data={
            "reviewed_control_ids": [control_id],
            "start": "2026-11-20T00:00:00+00:00",
            "end": "2026-11-20T01:00:00+00:00",
            "observations": [
                {
                    "title": "Observation",
                    "description": "desc",
                    "methods": ["EXAMINE"],
                    "collected_at": "2026-11-20T00:30:00+00:00",
                    "subject_uuids": [str(subject_uuid)],
                    "evidence": [
                        {
                            "title": "Evidence",
                            "description": "Evidence description",
                            "href": "https://example.test/evidence/concurrency",
                        }
                    ],
                }
            ],
            "findings": [
                {
                    "title": "Concurrent finding",
                    "description": "desc",
                    "target_type": "objective-id",
                    "target_id": "local-mfa-objective",
                    "status": "satisfied",
                    "related_observation_ids": [],
                }
            ],
        },
    )
    observation_id = updated["observations"][0]["id"]
    service.update_result(
        tenant_id,
        actor,
        result["id"],
        title="Concurrent version AR",
        description=None,
        working_data={
            "reviewed_control_ids": [control_id],
            "start": "2026-11-20T00:00:00+00:00",
            "end": "2026-11-20T01:00:00+00:00",
            "observations": updated["observations"],
            "findings": [
                {
                    "id": updated["findings"][0]["id"],
                    "title": "Concurrent finding",
                    "description": "desc",
                    "target_type": "objective-id",
                    "target_id": "local-mfa-objective",
                    "status": "satisfied",
                    "related_observation_ids": [str(observation_id)],
                }
            ],
        },
    )

    def create_version_once() -> dict:
        concurrent_service = AssessmentResultService(lambda: session_factory.begin())
        return concurrent_service.create_version(tenant_id, actor, result["id"])

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(create_version_once)
        second = executor.submit(create_version_once)
        outcomes = [first.result(), second.result()]

    assert sorted(item["created"] for item in outcomes) == [False, True]
    assert len({item["id"] for item in outcomes}) == 1


def test_assessment_result_rejects_stale_related_observation_reference(
    grc_service, session_factory
) -> None:
    (
        tenant_id,
        actor,
        system_id,
        plan,
        plan_version,
        control_id,
        subject_uuid,
    ) = _prepare_plan_version(grc_service, session_factory)
    service = AssessmentResultService(lambda: session_factory.begin())

    result = service.create_result(
        tenant_id,
        actor,
        system_id,
        assessment_plan_id=plan["id"],
        assessment_plan_version_id=plan_version["id"],
        title="Stale reference AR",
        description=None,
    )
    updated = service.update_result(
        tenant_id,
        actor,
        result["id"],
        title="Stale reference AR",
        description=None,
        working_data={
            "reviewed_control_ids": [control_id],
            "start": None,
            "end": None,
            "observations": [
                {
                    "title": "Observation",
                    "description": "desc",
                    "methods": ["EXAMINE"],
                    "collected_at": "2026-11-20T00:30:00+00:00",
                    "subject_uuids": [str(subject_uuid)],
                    "evidence": [],
                }
            ],
            "findings": [
                {
                    "title": "Local objective finding",
                    "description": "desc",
                    "target_type": "objective-id",
                    "target_id": "local-mfa-objective",
                    "status": "satisfied",
                    "related_observation_ids": [],
                }
            ],
        },
    )
    stale_observation_id = updated["observations"][0]["id"]

    with pytest.raises(InvalidAssessmentResult) as error:
        service.update_result(
            tenant_id,
            actor,
            result["id"],
            title="Stale reference AR",
            description=None,
            working_data={
                "reviewed_control_ids": [control_id],
                "start": None,
                "end": None,
                "observations": [],
                "findings": [
                    {
                        "title": "Stale relation",
                        "description": "desc",
                        "target_type": "objective-id",
                        "target_id": "local-mfa-objective",
                        "status": "satisfied",
                        "related_observation_ids": [str(stale_observation_id)],
                    }
                ],
            },
        )

    assert any(item["code"] == "unknown_related_observation" for item in error.value.diagnostics)


def test_assessment_result_rejects_reviewed_controls_outside_pinned_plan_scope(
    grc_service, session_factory
) -> None:
    context = _prepare_plan_scope_context(grc_service, session_factory, selected_control_count=1)
    service = context["ar_service"]
    result = service.create_result(
        context["tenant_id"],
        context["actor"],
        context["system_id"],
        assessment_plan_id=context["plan"]["id"],
        assessment_plan_version_id=context["plan_version"]["id"],
        title="Scope violation AR",
        description=None,
    )

    with pytest.raises(InvalidAssessmentResult) as error:
        service.update_result(
            context["tenant_id"],
            context["actor"],
            result["id"],
            title="Scope violation AR",
            description=None,
            working_data={
                "reviewed_control_ids": [context["controls"][1]],
                "observations": [],
                "findings": [],
                "start": None,
                "end": None,
            },
        )

    assert any(
        item["code"] == "control_outside_assessment_plan_scope"
        for item in error.value.diagnostics
    )


def test_assessment_result_rejects_statement_target_outside_actual_reviewed_scope(
    grc_service, session_factory
) -> None:
    context = _prepare_plan_scope_context(grc_service, session_factory, selected_control_count=2)
    service = context["ar_service"]
    result = service.create_result(
        context["tenant_id"],
        context["actor"],
        context["system_id"],
        assessment_plan_id=context["plan"]["id"],
        assessment_plan_version_id=context["plan_version"]["id"],
        title="Statement scope AR",
        description=None,
    )
    statement_target = next(
        item["statement_id"]
        for item in result["statement_options"]
        if item["control_id"] == context["controls"][1]
    )

    with pytest.raises(InvalidAssessmentResult) as error:
        service.update_result(
            context["tenant_id"],
            context["actor"],
            result["id"],
            title="Statement scope AR",
            description=None,
            working_data={
                "reviewed_control_ids": [context["controls"][0]],
                "observations": [],
                "findings": [
                    {
                        "title": "Out-of-scope statement",
                        "description": "desc",
                        "target_type": "statement-id",
                        "target_id": statement_target,
                        "status": "satisfied",
                        "related_observation_ids": [],
                    }
                ],
                "start": None,
                "end": None,
            },
        )

    assert any(
        item["code"] == "statement_target_outside_actual_scope"
        for item in error.value.diagnostics
    )


def test_assessment_result_rejects_local_objective_target_outside_actual_scope(
    grc_service, session_factory
) -> None:
    context = _prepare_plan_scope_context(
        grc_service,
        session_factory,
        selected_control_count=3,
        local_objectives=[
            {
                "objective_id": "local-control-b",
                "control_id": "ac-2",
                "description": "desc",
                "methods": ["EXAMINE"],
            }
        ],
    )
    service = context["ar_service"]
    result = service.create_result(
        context["tenant_id"],
        context["actor"],
        context["system_id"],
        assessment_plan_id=context["plan"]["id"],
        assessment_plan_version_id=context["plan_version"]["id"],
        title="Objective scope AR",
        description=None,
    )

    with pytest.raises(InvalidAssessmentResult) as error:
        service.update_result(
            context["tenant_id"],
            context["actor"],
            result["id"],
            title="Objective scope AR",
            description=None,
            working_data={
                "reviewed_control_ids": [context["controls"][0]],
                "observations": [],
                "findings": [
                    {
                        "title": "Out-of-scope objective",
                        "description": "desc",
                        "target_type": "objective-id",
                        "target_id": "local-control-b",
                        "status": "satisfied",
                        "related_observation_ids": [],
                    }
                ],
                "start": None,
                "end": None,
            },
        )

    assert any(
        item["code"] == "objective_target_outside_actual_scope"
        for item in error.value.diagnostics
    )


def test_assessment_result_rejects_subjects_outside_pinned_plan_selection(
    grc_service, session_factory
) -> None:
    context = _prepare_plan_scope_context(
        grc_service,
        session_factory,
        selected_control_count=1,
        selected_subject_indexes=(0,),
    )
    service = context["ar_service"]
    result = service.create_result(
        context["tenant_id"],
        context["actor"],
        context["system_id"],
        assessment_plan_id=context["plan"]["id"],
        assessment_plan_version_id=context["plan_version"]["id"],
        title="Subject scope AR",
        description=None,
    )

    with pytest.raises(InvalidAssessmentResult) as error:
        service.update_result(
            context["tenant_id"],
            context["actor"],
            result["id"],
            title="Subject scope AR",
            description=None,
            working_data={
                "reviewed_control_ids": [context["controls"][0]],
                "observations": [
                    {
                        "title": "Invalid subject reference",
                        "description": "desc",
                        "methods": ["EXAMINE"],
                        "collected_at": "2026-11-20T00:30:00+00:00",
                        "subject_uuids": [context["subjects"][1]],
                        "evidence": [],
                    }
                ],
                "findings": [],
                "start": None,
                "end": None,
            },
        )

    assert any(item["code"] == "unknown_subject_uuid" for item in error.value.diagnostics)


def test_assessment_result_allows_empty_subjects_when_plan_has_no_subject_selection(
    grc_service, session_factory
) -> None:
    context = _prepare_plan_scope_context(
        grc_service,
        session_factory,
        selected_control_count=1,
        selected_subject_indexes=(),
    )
    service = context["ar_service"]
    result = service.create_result(
        context["tenant_id"],
        context["actor"],
        context["system_id"],
        assessment_plan_id=context["plan"]["id"],
        assessment_plan_version_id=context["plan_version"]["id"],
        title="No-subject AR",
        description=None,
    )
    assert result["subject_options"] == []

    updated = service.update_result(
        context["tenant_id"],
        context["actor"],
        result["id"],
        title="No-subject AR",
        description=None,
        working_data={
            "reviewed_control_ids": [context["controls"][0]],
            "observations": [
                {
                    "title": "Observation without explicit subject",
                    "description": "desc",
                    "methods": ["EXAMINE"],
                    "collected_at": "2026-11-20T00:30:00+00:00",
                    "subject_uuids": [],
                    "evidence": [],
                }
            ],
            "findings": [],
            "start": None,
            "end": None,
        },
    )
    assert updated["observations"][0]["subject_uuids"] == []

    with pytest.raises(InvalidAssessmentResult) as error:
        service.update_result(
            context["tenant_id"],
            context["actor"],
            result["id"],
            title="No-subject AR",
            description=None,
            working_data={
                "reviewed_control_ids": [context["controls"][0]],
                "observations": [
                    {
                        "title": "Observation with disallowed subject",
                        "description": "desc",
                        "methods": ["EXAMINE"],
                        "collected_at": "2026-11-20T00:30:00+00:00",
                        "subject_uuids": [context["subjects"][0]],
                        "evidence": [],
                    }
                ],
                "findings": [],
                "start": None,
                "end": None,
            },
        )
    assert any(item["code"] == "unknown_subject_uuid" for item in error.value.diagnostics)


def test_assessment_result_requires_related_observations_for_validation_and_publication(
    grc_service, session_factory
) -> None:
    context = _prepare_plan_scope_context(
        grc_service,
        session_factory,
        selected_control_count=1,
        selected_subject_indexes=(0,),
        local_objectives=[
            {
                "objective_id": "local-a",
                "control_id": "ac-1",
                "description": "desc",
                "methods": ["EXAMINE"],
            }
        ],
    )
    service = context["ar_service"]
    result = service.create_result(
        context["tenant_id"],
        context["actor"],
        context["system_id"],
        assessment_plan_id=context["plan"]["id"],
        assessment_plan_version_id=context["plan_version"]["id"],
        title="Finding support AR",
        description=None,
    )
    service.update_result(
        context["tenant_id"],
        context["actor"],
        result["id"],
        title="Finding support AR",
        description=None,
        working_data={
            "reviewed_control_ids": [context["controls"][0]],
            "start": "2026-11-20T00:00:00+00:00",
            "end": "2026-11-20T01:00:00+00:00",
            "observations": [
                {
                    "title": "Observed evidence",
                    "description": "desc",
                    "methods": ["EXAMINE"],
                    "collected_at": "2026-11-20T00:30:00+00:00",
                    "subject_uuids": [context["subjects"][0]],
                    "evidence": [],
                }
            ],
            "findings": [
                {
                    "title": "Missing support link",
                    "description": "desc",
                    "target_type": "objective-id",
                    "target_id": "local-a",
                    "status": "satisfied",
                    "related_observation_ids": [],
                }
            ],
        },
    )

    validation = service.validate_result(context["tenant_id"], result["id"])
    assert validation["valid"] is False
    assert any(
        item["code"] == "finding_missing_related_observations"
        for item in validation["diagnostics"]
    )

    with pytest.raises(InvalidAssessmentResult) as publish_error:
        service.create_version(context["tenant_id"], context["actor"], result["id"])
    assert any(
        item["code"] == "finding_missing_related_observations"
        for item in publish_error.value.diagnostics
    )


def test_assessment_result_uses_pinned_plan_context_after_newer_plan_versions(
    grc_service, session_factory
) -> None:
    context = _prepare_plan_scope_context(
        grc_service,
        session_factory,
        selected_control_count=1,
        selected_subject_indexes=(0,),
        local_objectives=[
            {
                "objective_id": "local-a",
                "control_id": "ac-1",
                "description": "desc",
                "methods": ["EXAMINE"],
            }
        ],
    )
    service = context["ar_service"]
    result = service.create_result(
        context["tenant_id"],
        context["actor"],
        context["system_id"],
        assessment_plan_id=context["plan"]["id"],
        assessment_plan_version_id=context["plan_version"]["id"],
        title="Pinned context AR",
        description=None,
    )

    context["ap_service"].update_plan(
        context["tenant_id"],
        context["actor"],
        context["plan"]["id"],
        title="Scoped AP v2",
        description="changed scope",
        working_data={
            "control_ids": [context["controls"][1]],
            "source_objectives": [],
            "local_objectives": [
                {
                    "objective_id": "local-b",
                    "control_id": context["controls"][1],
                    "description": "desc",
                    "methods": ["EXAMINE"],
                }
            ],
            "subject_uuids": [context["subjects"][1]],
            "activities": [],
            "tasks": [],
            "roles": [],
            "parties": [],
            "terms": None,
        },
    )
    context["ap_service"].create_version(
        context["tenant_id"], context["actor"], context["plan"]["id"]
    )

    current = service.get_result(context["tenant_id"], result["id"])
    assert "local-a" in {item["objective_id"] for item in current["objective_options"]}
    assert "local-b" not in {item["objective_id"] for item in current["objective_options"]}


def test_assessment_result_exported_versions_remain_stable_after_hardening_checks(
    grc_service, session_factory
) -> None:
    (
        tenant_id,
        actor,
        system_id,
        plan,
        plan_version,
        control_id,
        subject_uuid,
    ) = _prepare_plan_version(grc_service, session_factory)
    service = AssessmentResultService(lambda: session_factory.begin())
    result = service.create_result(
        tenant_id,
        actor,
        system_id,
        assessment_plan_id=plan["id"],
        assessment_plan_version_id=plan_version["id"],
        title="Stable export AR",
        description=None,
    )
    updated = service.update_result(
        tenant_id,
        actor,
        result["id"],
        title="Stable export AR",
        description=None,
        working_data={
            "reviewed_control_ids": [control_id],
            "start": "2026-11-20T00:00:00+00:00",
            "end": "2026-11-20T01:00:00+00:00",
            "observations": [
                {
                    "title": "Observation",
                    "description": "desc",
                    "methods": ["EXAMINE"],
                    "collected_at": "2026-11-20T00:30:00+00:00",
                    "subject_uuids": [str(subject_uuid)],
                    "evidence": [],
                }
            ],
            "findings": [
                {
                    "title": "Supported finding",
                    "description": "desc",
                    "target_type": "objective-id",
                    "target_id": "local-mfa-objective",
                    "status": "satisfied",
                    "related_observation_ids": [],
                }
            ],
        },
    )
    observation_id = updated["observations"][0]["id"]
    service.update_result(
        tenant_id,
        actor,
        result["id"],
        title="Stable export AR",
        description=None,
        working_data={
            "reviewed_control_ids": [control_id],
            "start": "2026-11-20T00:00:00+00:00",
            "end": "2026-11-20T01:00:00+00:00",
            "observations": updated["observations"],
            "findings": [
                {
                    "id": updated["findings"][0]["id"],
                    "title": "Supported finding",
                    "description": "desc",
                    "target_type": "objective-id",
                    "target_id": "local-mfa-objective",
                    "status": "satisfied",
                    "related_observation_ids": [str(observation_id)],
                }
            ],
        },
    )
    version = service.create_version(tenant_id, actor, result["id"])
    exported_before = service.export_version(tenant_id, result["id"], version["id"])

    service.update_result(
        tenant_id,
        actor,
        result["id"],
        title="Stable export AR",
        description=None,
        working_data={
            "reviewed_control_ids": [control_id],
            "start": "2026-11-20T00:00:00+00:00",
            "end": "2026-11-20T01:00:00+00:00",
            "observations": updated["observations"],
            "findings": [
                {
                    "id": updated["findings"][0]["id"],
                    "title": "Now missing support",
                    "description": "desc",
                    "target_type": "objective-id",
                    "target_id": "local-mfa-objective",
                    "status": "satisfied",
                    "related_observation_ids": [],
                }
            ],
        },
    )

    exported_after = service.export_version(tenant_id, result["id"], version["id"])
    assert exported_before == exported_after




