# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.application.assessment_plans import AssessmentPlanService
from app.application.assessment_results import (
    AssessmentResultImportConflict,
    AssessmentResultService,
    InvalidAssessmentResult,
    StaleAssessmentResultUpdate,
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
from app.persistence.models import AssessmentResultRecord, CatalogControlIndexRecord

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


def _expected_version(ap_service: AssessmentPlanService, tenant_id: UUID, plan_id: UUID) -> int:
    return int(ap_service.get_plan(tenant_id, plan_id)["concurrency_version"])


def _result_expected_version(
    ar_service: AssessmentResultService, tenant_id: UUID, result_id: UUID
) -> int:
    return int(ar_service.get_result(tenant_id, result_id)["concurrency_version"])


def _update_result(
    ar_service: AssessmentResultService,
    tenant_id: UUID,
    actor: UUID,
    result_id: UUID,
    *,
    title: str,
    description: str | None,
    working_data: dict[str, object],
) -> dict[str, object]:
    return ar_service.update_result(
        tenant_id,
        actor,
        result_id,
        expected_version=_result_expected_version(ar_service, tenant_id, result_id),
        title=title,
        description=description,
        working_data=working_data,
    )


def _publish_result(
    ar_service: AssessmentResultService,
    tenant_id: UUID,
    actor: UUID,
    result_id: UUID,
    *,
    expected_version: int | None = None,
) -> dict[str, object]:
    return ar_service.create_version(
        tenant_id,
        actor,
        result_id,
        expected_version=(
            expected_version
            if expected_version is not None
            else _result_expected_version(ar_service, tenant_id, result_id)
        ),
    )


@contextmanager
def _bound_scope(session):
    yield session


def _backend_pid(session) -> int:
    return int(session.execute(text("select pg_backend_pid()")).scalar_one())


def _assert_blocked_by(
    session_factory,
    *,
    blocked_pid: int,
    blocker_pid: int,
    attempts: int = 200,
) -> None:
    with session_factory.begin() as observer:
        for _ in range(attempts):
            blockers = observer.execute(
                text("select pg_blocking_pids(:blocked_pid)"),
                {"blocked_pid": blocked_pid},
            ).scalar_one()
            blocking_pids = {int(item) for item in (blockers or [])}
            if blocker_pid in blocking_pids:
                return
    pytest.fail(
        f"Backend {blocked_pid} was not observed blocked by backend {blocker_pid}."
    )


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
    included = ssp_service.associate_implementation(
        tenant.id,
        actor,
        ssp["id"],
        implementation.id,
        component["id"],
        expected_version=ssp["concurrency_version"],
    )
    ssp["concurrency_version"] = included["concurrency_version"]
    ssp_version = ssp_service.create_version(
        tenant.id,
        actor,
        ssp["id"],
        expected_version=ssp["concurrency_version"],
    )

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
        expected_version=_expected_version(ap_service, tenant.id, plan["id"]),
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
    plan_version = ap_service.create_version(
        tenant.id,
        actor,
        plan["id"],
        expected_version=_expected_version(ap_service, tenant.id, plan["id"]),
    )
    return tenant.id, actor, system["id"], plan, plan_version, controls[0], UUID(str(subject_uuid))


def _prepare_plan_scope_context(
    grc_service,
    session_factory,
    *,
    selected_control_count: int = 2,
    selected_control_ids: list[str] | None = None,
    selected_subject_indexes: tuple[int, ...] = (0,),
    source_objectives: list[dict[str, object]] | None = None,
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
    included = ssp_service.associate_implementation(
        tenant.id,
        actor,
        ssp["id"],
        implementation.id,
        component_a["id"],
        expected_version=ssp["concurrency_version"],
    )
    ssp["concurrency_version"] = included["concurrency_version"]
    ssp_version = ssp_service.create_version(
        tenant.id,
        actor,
        ssp["id"],
        expected_version=ssp["concurrency_version"],
    )

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
        expected_version=_expected_version(ap_service, tenant.id, plan["id"]),
        title=plan["title"],
        description=plan["description"],
        working_data={
            "control_ids": (
                selected_control_ids
                if selected_control_ids is not None
                else controls[:selected_control_count]
            ),
            "source_objectives": source_objectives or [],
            "local_objectives": local_objectives or [],
            "subject_uuids": selected_subjects,
            "activities": [],
            "tasks": [],
            "roles": [],
            "parties": [],
            "terms": None,
        },
    )
    plan_version = ap_service.create_version(
        tenant.id,
        actor,
        plan["id"],
        expected_version=_expected_version(ap_service, tenant.id, plan["id"]),
    )
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


def _working_payload(
    *,
    control_id: str,
    observations: list[dict],
    findings: list[dict],
    start: str | None = "2026-11-20T00:00:00+00:00",
    end: str | None = "2026-11-20T01:00:00+00:00",
) -> dict[str, object]:
    return {
        "reviewed_control_ids": [control_id],
        "start": start,
        "end": end,
        "observations": observations,
        "findings": findings,
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

    updated = _update_result(service,
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

    updated = _update_result(service,
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

    version = _publish_result(service, tenant_id, actor, result["id"])
    assert version["created"] is True
    assert version["oscal_version"] == "1.2.1"
    exported = service.export_version(tenant_id, result["id"], version["id"])
    assert exported["assessment-results"]["import-ap"]["href"].endswith(
        f"/{plan_version['id']}/export"
    )

    unchanged = _publish_result(service, tenant_id, actor, result["id"])
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
        _update_result(service,
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
    grc_service, session_factory, monkeypatch
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
    updated = _update_result(service,
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
    _update_result(service,
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

    token = _result_expected_version(service, tenant_id, result["id"])
    release = threading.Barrier(3)
    winner_holding_lock = threading.Event()
    gate_release = threading.Event()
    state_lock = threading.Lock()
    backend_pids: dict[str, int] = {}
    winner_pid: dict[str, int | None] = {"value": None}
    original_get_result = AssessmentResultService._get_result

    def _gated_get_result(session, tenant_id, result_id, *, lock=False):
        loaded = original_get_result(session, tenant_id, result_id, lock=lock)
        if lock:
            pid = _backend_pid(session)
            with state_lock:
                if winner_pid["value"] is None:
                    winner_pid["value"] = pid
                    is_winner = True
                else:
                    is_winner = False
            if is_winner:
                winner_holding_lock.set()
                assert gate_release.wait(timeout=5)
        return loaded

    monkeypatch.setattr(AssessmentResultService, "_get_result", staticmethod(_gated_get_result))

    def create_version_once(worker: str) -> dict[str, object]:
        with session_factory.begin() as thread_session:
            with state_lock:
                backend_pids[worker] = _backend_pid(thread_session)
            concurrent_service = AssessmentResultService(lambda: _bound_scope(thread_session))
            release.wait(timeout=5)
            return _publish_result(
                concurrent_service,
                tenant_id,
                actor,
                result["id"],
                expected_version=token,
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(create_version_once, "a")
        second = executor.submit(create_version_once, "b")
        release.wait(timeout=5)
        try:
            assert winner_holding_lock.wait(timeout=5)
            winner = winner_pid["value"]
            assert winner is not None
            blocked = next(pid for pid in backend_pids.values() if pid != winner)
            _assert_blocked_by(
                session_factory,
                blocked_pid=blocked,
                blocker_pid=winner,
            )
        finally:
            gate_release.set()

    published = []
    stale = []
    for future in [first, second]:
        try:
            published.append(future.result())
        except StaleAssessmentResultUpdate as error:
            stale.append(error)

    assert len(published) == 1
    assert published[0]["created"] is True
    assert len(stale) == 1
    assert stale[0].expected_version == token
    assert stale[0].current_version == token + 1

    versions = service.list_versions(tenant_id, result["id"])
    assert len(versions) == 1
    assert versions[0]["id"] == published[0]["id"]


def test_assessment_result_update_rejects_stale_token_under_concurrent_transactions(
    grc_service, session_factory, monkeypatch
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
        title="Concurrent AR",
        description="Concurrency check",
    )
    token = _result_expected_version(service, tenant_id, result["id"])
    release = threading.Barrier(3)
    winner_holding_lock = threading.Event()
    gate_release = threading.Event()
    state_lock = threading.Lock()
    backend_pids: dict[str, int] = {}
    winner_pid: dict[str, int | None] = {"value": None}
    original_get_result = AssessmentResultService._get_result

    def _gated_get_result(session, tenant_id, result_id, *, lock=False):
        loaded = original_get_result(session, tenant_id, result_id, lock=lock)
        if lock:
            pid = _backend_pid(session)
            with state_lock:
                if winner_pid["value"] is None:
                    winner_pid["value"] = pid
                    is_winner = True
                else:
                    is_winner = False
            if is_winner:
                winner_holding_lock.set()
                assert gate_release.wait(timeout=5)
        return loaded

    monkeypatch.setattr(AssessmentResultService, "_get_result", staticmethod(_gated_get_result))

    def _attempt_update(title: str, worker: str) -> str:
        with session_factory.begin() as thread_session:
            with state_lock:
                backend_pids[worker] = _backend_pid(thread_session)
            concurrent_service = AssessmentResultService(lambda: _bound_scope(thread_session))
            release.wait(timeout=5)
            concurrent_service.update_result(
                tenant_id,
                actor,
                result["id"],
                expected_version=token,
                title=title,
                description="Concurrency check",
                working_data={
                    "reviewed_control_ids": [control_id],
                    "start": None,
                    "end": None,
                    "observations": [],
                    "findings": [],
                },
            )
            return title

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(_attempt_update, "Concurrent AR A", "a"),
            executor.submit(_attempt_update, "Concurrent AR B", "b"),
        ]
        release.wait(timeout=5)
        try:
            assert winner_holding_lock.wait(timeout=5)
            winner = winner_pid["value"]
            assert winner is not None
            blocked = next(pid for pid in backend_pids.values() if pid != winner)
            _assert_blocked_by(
                session_factory,
                blocked_pid=blocked,
                blocker_pid=winner,
            )
        finally:
            gate_release.set()

    winners = []
    stale = []
    for future in futures:
        try:
            winners.append(future.result())
        except StaleAssessmentResultUpdate as error:
            stale.append(error)

    assert len(winners) == 1
    assert len(stale) == 1
    assert stale[0].expected_version == token
    assert stale[0].current_version == token + 1

    persisted = service.get_result(tenant_id, result["id"])
    assert persisted["concurrency_version"] == token + 1
    assert persisted["title"] == winners[0]


def test_assessment_result_publish_rejects_stale_token_under_concurrent_transactions(
    grc_service, session_factory, monkeypatch
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
        title="Concurrent AR publish",
        description="Concurrency check",
    )
    updated = _update_result(service,
        tenant_id,
        actor,
        result["id"],
        title="Concurrent AR publish",
        description="Concurrency check",
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
    _update_result(service,
        tenant_id,
        actor,
        result["id"],
        title="Concurrent AR publish",
        description="Concurrency check",
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
    token = _result_expected_version(service, tenant_id, result["id"])
    release = threading.Barrier(3)
    winner_holding_lock = threading.Event()
    gate_release = threading.Event()
    state_lock = threading.Lock()
    backend_pids: dict[str, int] = {}
    winner_pid: dict[str, int | None] = {"value": None}
    original_get_result = AssessmentResultService._get_result

    def _gated_get_result(session, tenant_id, result_id, *, lock=False):
        loaded = original_get_result(session, tenant_id, result_id, lock=lock)
        if lock:
            pid = _backend_pid(session)
            with state_lock:
                if winner_pid["value"] is None:
                    winner_pid["value"] = pid
                    is_winner = True
                else:
                    is_winner = False
            if is_winner:
                winner_holding_lock.set()
                assert gate_release.wait(timeout=5)
        return loaded

    monkeypatch.setattr(AssessmentResultService, "_get_result", staticmethod(_gated_get_result))

    def _attempt_publish(worker: str) -> dict[str, object]:
        with session_factory.begin() as thread_session:
            with state_lock:
                backend_pids[worker] = _backend_pid(thread_session)
            concurrent_service = AssessmentResultService(lambda: _bound_scope(thread_session))
            release.wait(timeout=5)
            return concurrent_service.create_version(
                tenant_id,
                actor,
                result["id"],
                expected_version=token,
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(_attempt_publish, "a"), executor.submit(_attempt_publish, "b")]
        release.wait(timeout=5)
        try:
            assert winner_holding_lock.wait(timeout=5)
            winner = winner_pid["value"]
            assert winner is not None
            blocked = next(pid for pid in backend_pids.values() if pid != winner)
            _assert_blocked_by(
                session_factory,
                blocked_pid=blocked,
                blocker_pid=winner,
            )
        finally:
            gate_release.set()

    published = []
    stale = []
    for future in futures:
        try:
            published.append(future.result())
        except StaleAssessmentResultUpdate as error:
            stale.append(error)

    assert len(published) == 1
    assert published[0]["created"] is True
    assert len(stale) == 1
    assert stale[0].expected_version == token
    assert stale[0].current_version == token + 1

    versions = service.list_versions(tenant_id, result["id"])
    assert len(versions) == 1
    assert versions[0]["id"] == published[0]["id"]

    persisted = service.get_result(tenant_id, result["id"])
    assert persisted["concurrency_version"] == token + 1


def test_assessment_result_update_translates_mapper_stale_error(
    grc_service, session_factory, monkeypatch
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
    created = service.create_result(
        tenant_id,
        actor,
        system_id,
        assessment_plan_id=plan["id"],
        assessment_plan_version_id=plan_version["id"],
        title="Forced mapper stale",
        description=None,
    )
    token = created["concurrency_version"]

    original_get_result = AssessmentResultService._get_result
    loaded_version_unchanged = {"value": False}

    def _stale_mapper_version_get_result(session, tenant_id, result_id, *, lock=False):
        loaded = original_get_result(session, tenant_id, result_id, lock=lock)
        if lock:
            loaded_version = int(loaded.concurrency_version)
            session.execute(
                update(AssessmentResultRecord)
                .where(
                    AssessmentResultRecord.tenant_id == tenant_id,
                    AssessmentResultRecord.id == result_id,
                )
                .values(
                    concurrency_version=AssessmentResultRecord.concurrency_version + 1,
                )
                .execution_options(synchronize_session=False)
            )
            loaded_version_unchanged["value"] = int(loaded.concurrency_version) == loaded_version
        return loaded

    monkeypatch.setattr(
        AssessmentResultService,
        "_get_result",
        staticmethod(_stale_mapper_version_get_result),
    )

    stale_service = AssessmentResultService(lambda: session_factory.begin())
    with pytest.raises(StaleAssessmentResultUpdate) as error:
        stale_service.update_result(
            tenant_id,
            actor,
            created["id"],
            expected_version=token,
            title="Forced mapper stale",
            description=None,
            working_data={
                "reviewed_control_ids": [control_id],
                "start": None,
                "end": None,
                "observations": [],
                "findings": [],
            },
        )
    persisted = service.get_result(tenant_id, created["id"])
    assert loaded_version_unchanged["value"] is True
    assert isinstance(error.value.__cause__, StaleDataError)
    assert error.value.expected_version == token
    assert error.value.current_version == token
    assert persisted["concurrency_version"] == token
    assert persisted["title"] == created["title"]


def test_assessment_result_publish_translates_mapper_stale_error(
    grc_service, session_factory, monkeypatch
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
    created = service.create_result(
        tenant_id,
        actor,
        system_id,
        assessment_plan_id=plan["id"],
        assessment_plan_version_id=plan_version["id"],
        title="Forced mapper stale publish",
        description=None,
    )
    seeded = _update_result(
        service,
        tenant_id,
        actor,
        created["id"],
        title="Forced mapper stale publish",
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
                    "title": "Finding",
                    "description": "desc",
                    "target_type": "objective-id",
                    "target_id": "local-mfa-objective",
                    "status": "satisfied",
                    "related_observation_ids": [],
                }
            ],
        },
    )
    observation_id = str(seeded["observations"][0]["id"])
    _update_result(
        service,
        tenant_id,
        actor,
        created["id"],
        title="Forced mapper stale publish",
        description=None,
        working_data={
            "reviewed_control_ids": [control_id],
            "start": "2026-11-20T00:00:00+00:00",
            "end": "2026-11-20T01:00:00+00:00",
            "observations": seeded["observations"],
            "findings": [
                {
                    "id": seeded["findings"][0]["id"],
                    "title": "Finding",
                    "description": "desc",
                    "target_type": "objective-id",
                    "target_id": "local-mfa-objective",
                    "status": "satisfied",
                    "related_observation_ids": [observation_id],
                }
            ],
        },
    )
    token = _result_expected_version(service, tenant_id, created["id"])
    assert service.list_versions(tenant_id, created["id"]) == []

    original_get_result = AssessmentResultService._get_result
    loaded_version_unchanged = {"value": False}

    def _stale_mapper_version_get_result(session, tenant_id, result_id, *, lock=False):
        loaded = original_get_result(session, tenant_id, result_id, lock=lock)
        if lock:
            loaded_version = int(loaded.concurrency_version)
            session.execute(
                update(AssessmentResultRecord)
                .where(
                    AssessmentResultRecord.tenant_id == tenant_id,
                    AssessmentResultRecord.id == result_id,
                )
                .values(
                    concurrency_version=AssessmentResultRecord.concurrency_version + 1,
                )
                .execution_options(synchronize_session=False)
            )
            loaded_version_unchanged["value"] = int(loaded.concurrency_version) == loaded_version
        return loaded

    monkeypatch.setattr(
        AssessmentResultService,
        "_get_result",
        staticmethod(_stale_mapper_version_get_result),
    )

    stale_service = AssessmentResultService(lambda: session_factory.begin())
    with pytest.raises(StaleAssessmentResultUpdate) as error:
        stale_service.create_version(
            tenant_id,
            actor,
            created["id"],
            expected_version=token,
        )
    assert loaded_version_unchanged["value"] is True
    assert isinstance(error.value.__cause__, StaleDataError)
    assert error.value.expected_version == token
    assert error.value.current_version == token
    assert service.list_versions(tenant_id, created["id"]) == []
    assert service.get_result(tenant_id, created["id"])["concurrency_version"] == token


def test_assessment_result_nested_only_update_advances_concurrency_version(
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
    created = service.create_result(
        tenant_id,
        actor,
        system_id,
        assessment_plan_id=plan["id"],
        assessment_plan_version_id=plan_version["id"],
        title="Nested-only version bump",
        description=None,
    )
    seeded = _update_result(
        service,
        tenant_id,
        actor,
        created["id"],
        title="Nested-only version bump",
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
                    "evidence": [
                        {
                            "title": "Evidence",
                            "description": "old",
                            "href": "https://example.test/evidence/1",
                        }
                    ],
                }
            ],
            "findings": [],
        },
    )
    token = seeded["concurrency_version"]
    nested_change = _update_result(
        service,
        tenant_id,
        actor,
        created["id"],
        title=seeded["title"],
        description=seeded["description"],
        working_data={
            "reviewed_control_ids": seeded["reviewed_control_ids"],
            "start": seeded["start"],
            "end": seeded["end"],
            "observations": [
                {
                    **seeded["observations"][0],
                    "evidence": [
                        {
                            **seeded["observations"][0]["evidence"][0],
                            "description": "new",
                        }
                    ],
                }
            ],
            "findings": seeded["findings"],
        },
    )

    assert nested_change["concurrency_version"] == token + 1


def test_assessment_result_idempotent_publish_reuses_snapshot_without_token_increment(
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
        title="Idempotent publish",
        description=None,
    )
    updated = _update_result(
        service,
        tenant_id,
        actor,
        result["id"],
        title="Idempotent publish",
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
                    "title": "Finding",
                    "description": "desc",
                    "target_type": "objective-id",
                    "target_id": "local-mfa-objective",
                    "status": "satisfied",
                    "related_observation_ids": [],
                }
            ],
        },
    )
    observation_id = str(updated["observations"][0]["id"])
    _update_result(
        service,
        tenant_id,
        actor,
        result["id"],
        title="Idempotent publish",
        description=None,
        working_data={
            "reviewed_control_ids": [control_id],
            "start": "2026-11-20T00:00:00+00:00",
            "end": "2026-11-20T01:00:00+00:00",
            "observations": updated["observations"],
            "findings": [
                {
                    "id": updated["findings"][0]["id"],
                    "title": "Finding",
                    "description": "desc",
                    "target_type": "objective-id",
                    "target_id": "local-mfa-objective",
                    "status": "satisfied",
                    "related_observation_ids": [observation_id],
                }
            ],
        },
    )

    first = _publish_result(service, tenant_id, actor, result["id"])
    token_after_first = int(first["concurrency_version"])
    second = _publish_result(
        service,
        tenant_id,
        actor,
        result["id"],
        expected_version=token_after_first,
    )

    assert second["created"] is False
    assert second["id"] == first["id"]
    assert second["concurrency_version"] == token_after_first
    assert service.get_result(tenant_id, result["id"])["concurrency_version"] == token_after_first
    assert len(service.list_versions(tenant_id, result["id"])) == 1


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
    updated = _update_result(service,
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
        _update_result(service,
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
        _update_result(service,
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
        _update_result(service,
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
    assert any(
        item.get("path") == "$.findings[0].target_id"
        for item in error.value.diagnostics
        if item["code"] == "statement_target_outside_actual_scope"
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
        _update_result(service,
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
    assert any(
        item.get("path") == "$.findings[0].target_id"
        for item in error.value.diagnostics
        if item["code"] == "objective_target_outside_actual_scope"
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
        _update_result(service,
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

    updated = _update_result(service,
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
        _update_result(service,
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
    _update_result(service,
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
        _publish_result(service, context["tenant_id"], context["actor"], result["id"])
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
        expected_version=_expected_version(
            context["ap_service"], context["tenant_id"], context["plan"]["id"]
        ),
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
        context["tenant_id"],
        context["actor"],
        context["plan"]["id"],
        expected_version=_expected_version(
            context["ap_service"], context["tenant_id"], context["plan"]["id"]
        ),
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
    updated = _update_result(service,
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
    _update_result(service,
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
    version = _publish_result(service, tenant_id, actor, result["id"])
    exported_before = service.export_version(tenant_id, result["id"], version["id"])

    _update_result(service,
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


def test_assessment_result_reorder_preserves_explicit_observation_ids(
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
        title="Reorder IDs AR",
        description=None,
    )
    updated = _update_result(service,
        tenant_id,
        actor,
        result["id"],
        title="Reorder IDs AR",
        description=None,
        working_data=_working_payload(
            control_id=control_id,
            observations=[
                {
                    "title": "Observation A",
                    "description": "desc",
                    "methods": ["EXAMINE"],
                    "collected_at": "2026-11-20T00:30:00+00:00",
                    "subject_uuids": [str(subject_uuid)],
                    "evidence": [],
                },
                {
                    "title": "Observation B",
                    "description": "desc",
                    "methods": ["EXAMINE"],
                    "collected_at": "2026-11-20T00:40:00+00:00",
                    "subject_uuids": [str(subject_uuid)],
                    "evidence": [],
                },
            ],
            findings=[],
        ),
    )
    first_id = str(updated["observations"][0]["id"])
    second_id = str(updated["observations"][1]["id"])

    reordered = _update_result(service,
        tenant_id,
        actor,
        result["id"],
        title="Reorder IDs AR",
        description=None,
        working_data=_working_payload(
            control_id=control_id,
            observations=[updated["observations"][1], updated["observations"][0]],
            findings=[],
        ),
    )
    assert str(reordered["observations"][0]["id"]) == second_id
    assert str(reordered["observations"][1]["id"]) == first_id


def test_assessment_result_replacement_without_ids_generates_new_nested_ids(
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
        title="Replacement IDs AR",
        description=None,
    )

    updated = _update_result(service,
        tenant_id,
        actor,
        result["id"],
        title="Replacement IDs AR",
        description=None,
        working_data=_working_payload(
            control_id=control_id,
            observations=[
                {
                    "title": "Observation",
                    "description": "desc",
                    "methods": ["EXAMINE"],
                    "collected_at": "2026-11-20T00:30:00+00:00",
                    "subject_uuids": [str(subject_uuid)],
                    "evidence": [
                        {
                            "title": "Evidence",
                            "description": "desc",
                            "href": "https://example.test/evidence/1",
                        }
                    ],
                }
            ],
            findings=[
                {
                    "title": "Finding",
                    "description": "desc",
                    "target_type": "objective-id",
                    "target_id": "local-mfa-objective",
                    "status": "satisfied",
                    "related_observation_ids": [],
                }
            ],
        ),
    )

    old_observation_id = str(updated["observations"][0]["id"])
    old_evidence_id = str(updated["observations"][0]["evidence"][0]["id"])
    old_finding_id = str(updated["findings"][0]["id"])

    replaced = _update_result(service,
        tenant_id,
        actor,
        result["id"],
        title="Replacement IDs AR",
        description=None,
        working_data=_working_payload(
            control_id=control_id,
            observations=[
                {
                    "title": "Replacement observation",
                    "description": "desc",
                    "methods": ["EXAMINE"],
                    "collected_at": "2026-11-20T00:35:00+00:00",
                    "subject_uuids": [str(subject_uuid)],
                    "evidence": [
                        {
                            "title": "Replacement evidence",
                            "description": "desc",
                            "href": "https://example.test/evidence/2",
                        }
                    ],
                }
            ],
            findings=[
                {
                    "title": "Replacement finding",
                    "description": "desc",
                    "target_type": "objective-id",
                    "target_id": "local-mfa-objective",
                    "status": "satisfied",
                    "related_observation_ids": [],
                }
            ],
        ),
    )

    assert str(replaced["observations"][0]["id"]) != old_observation_id
    assert str(replaced["observations"][0]["evidence"][0]["id"]) != old_evidence_id
    assert str(replaced["findings"][0]["id"]) != old_finding_id


def test_assessment_result_replacement_observation_does_not_retarget_existing_finding(
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
        title="No retarget AR",
        description=None,
    )
    updated = _update_result(service,
        tenant_id,
        actor,
        result["id"],
        title="No retarget AR",
        description=None,
        working_data=_working_payload(
            control_id=control_id,
            observations=[
                {
                    "title": "Observation",
                    "description": "desc",
                    "methods": ["EXAMINE"],
                    "collected_at": "2026-11-20T00:30:00+00:00",
                    "subject_uuids": [str(subject_uuid)],
                    "evidence": [],
                }
            ],
            findings=[
                {
                    "title": "Finding",
                    "description": "desc",
                    "target_type": "objective-id",
                    "target_id": "local-mfa-objective",
                    "status": "satisfied",
                    "related_observation_ids": [],
                }
            ],
        ),
    )
    observation_id = str(updated["observations"][0]["id"])
    finding_id = str(updated["findings"][0]["id"])

    linked = _update_result(service,
        tenant_id,
        actor,
        result["id"],
        title="No retarget AR",
        description=None,
        working_data=_working_payload(
            control_id=control_id,
            observations=updated["observations"],
            findings=[
                {
                    "id": finding_id,
                    "title": "Finding",
                    "description": "desc",
                    "target_type": "objective-id",
                    "target_id": "local-mfa-objective",
                    "status": "satisfied",
                    "related_observation_ids": [observation_id],
                }
            ],
        ),
    )

    with pytest.raises(InvalidAssessmentResult) as error:
        _update_result(service,
            tenant_id,
            actor,
            result["id"],
            title="No retarget AR",
            description=None,
            working_data=_working_payload(
                control_id=control_id,
                observations=[
                    {
                        "title": "Replacement",
                        "description": "desc",
                        "methods": ["EXAMINE"],
                        "collected_at": "2026-11-20T00:45:00+00:00",
                        "subject_uuids": [str(subject_uuid)],
                        "evidence": [],
                    }
                ],
                findings=linked["findings"],
            ),
        )
    assert any(item["code"] == "unknown_related_observation" for item in error.value.diagnostics)


def test_assessment_result_rejects_duplicate_evidence_uuid_across_document(
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
        title="Duplicate evidence AR",
        description=None,
    )
    shared = str(uuid4())
    with pytest.raises(InvalidAssessmentResult) as error:
        _update_result(service,
            tenant_id,
            actor,
            result["id"],
            title="Duplicate evidence AR",
            description=None,
            working_data=_working_payload(
                control_id=control_id,
                observations=[
                    {
                        "title": "Observation 1",
                        "description": "desc",
                        "methods": ["EXAMINE"],
                        "collected_at": "2026-11-20T00:30:00+00:00",
                        "subject_uuids": [str(subject_uuid)],
                        "evidence": [
                            {
                                "id": shared,
                                "title": "Evidence 1",
                                "description": "desc",
                                "href": "https://example.test/evidence/1",
                            }
                        ],
                    },
                    {
                        "title": "Observation 2",
                        "description": "desc",
                        "methods": ["EXAMINE"],
                        "collected_at": "2026-11-20T00:40:00+00:00",
                        "subject_uuids": [str(subject_uuid)],
                        "evidence": [
                            {
                                "id": shared,
                                "title": "Evidence 2",
                                "description": "desc",
                                "href": "https://example.test/evidence/2",
                            }
                        ],
                    },
                ],
                findings=[],
            ),
        )
    assert any(
        item["code"] == "duplicate_evidence_ids_document" for item in error.value.diagnostics
    )


def test_assessment_result_rejects_duplicate_observation_and_finding_ids(
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
        title="Duplicate IDs AR",
        description=None,
    )
    duplicate_observation_id = str(uuid4())
    duplicate_finding_id = str(uuid4())

    with pytest.raises(InvalidAssessmentResult) as error:
        _update_result(service,
            tenant_id,
            actor,
            result["id"],
            title="Duplicate IDs AR",
            description=None,
            working_data=_working_payload(
                control_id=control_id,
                observations=[
                    {
                        "id": duplicate_observation_id,
                        "title": "Observation 1",
                        "description": "desc",
                        "methods": ["EXAMINE"],
                        "collected_at": "2026-11-20T00:30:00+00:00",
                        "subject_uuids": [str(subject_uuid)],
                        "evidence": [],
                    },
                    {
                        "id": duplicate_observation_id,
                        "title": "Observation 2",
                        "description": "desc",
                        "methods": ["EXAMINE"],
                        "collected_at": "2026-11-20T00:40:00+00:00",
                        "subject_uuids": [str(subject_uuid)],
                        "evidence": [],
                    },
                ],
                findings=[
                    {
                        "id": duplicate_finding_id,
                        "title": "Finding 1",
                        "description": "desc",
                        "target_type": "objective-id",
                        "target_id": "local-mfa-objective",
                        "status": "satisfied",
                        "related_observation_ids": [],
                    },
                    {
                        "id": duplicate_finding_id,
                        "title": "Finding 2",
                        "description": "desc",
                        "target_type": "objective-id",
                        "target_id": "local-mfa-objective",
                        "status": "satisfied",
                        "related_observation_ids": [],
                    },
                ],
            ),
        )

    codes = {item["code"] for item in error.value.diagnostics}
    assert "duplicate_observation_ids" in codes
    assert "duplicate_finding_ids" in codes


def test_assessment_result_rejects_cross_entity_uuid_collisions(
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
        title="Cross-entity UUID AR",
        description=None,
    )
    shared_id = str(uuid4())

    with pytest.raises(InvalidAssessmentResult) as error:
        _update_result(service,
            tenant_id,
            actor,
            result["id"],
            title="Cross-entity UUID AR",
            description=None,
            working_data=_working_payload(
                control_id=control_id,
                observations=[
                    {
                        "id": shared_id,
                        "title": "Observation",
                        "description": "desc",
                        "methods": ["EXAMINE"],
                        "collected_at": "2026-11-20T00:30:00+00:00",
                        "subject_uuids": [str(subject_uuid)],
                        "evidence": [
                            {
                                "id": shared_id,
                                "title": "Evidence",
                                "description": "desc",
                                "href": "https://example.test/evidence/collision",
                            }
                        ],
                    }
                ],
                findings=[
                    {
                        "id": shared_id,
                        "title": "Finding",
                        "description": "desc",
                        "target_type": "objective-id",
                        "target_id": "local-mfa-objective",
                        "status": "satisfied",
                        "related_observation_ids": [],
                    }
                ],
            ),
        )

    assert any(
        item["code"] == "duplicate_authored_entity_ids"
        for item in error.value.diagnostics
    )


def test_assessment_result_rejects_entities_reusing_assessment_result_uuid_on_publish(
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
        title="Result UUID collision AR",
        description=None,
    )

    with session_factory.begin() as session:
        record = session.scalar(
            select(AssessmentResultRecord).where(
                AssessmentResultRecord.tenant_id == tenant_id,
                AssessmentResultRecord.id == result["id"],
            )
        )
        assert record is not None
        record.working_data = {
            "reviewed_control_ids": [control_id],
            "start": None,
            "end": None,
            "observations": [
                {
                    "id": str(result["id"]),
                    "title": "Observation",
                    "description": "desc",
                    "methods": ["EXAMINE"],
                    "collected_at": "2026-11-20T00:30:00+00:00",
                    "subject_uuids": [],
                    "evidence": [],
                }
            ],
            "findings": [],
        }

    with pytest.raises(InvalidAssessmentResult) as publish_error:
        _publish_result(service, tenant_id, actor, result["id"])

    assert any(
        item["code"] == "duplicate_authored_entity_ids"
        for item in publish_error.value.diagnostics
    )
    assert service.list_versions(tenant_id, result["id"]) == []


def test_assessment_result_rejects_ambiguous_statement_targets_even_when_actual_scope_is_narrowed(
    grc_service, session_factory
) -> None:
    catalog = json.loads(FIXTURE_PATH.read_text())
    controls = catalog["catalog"]["groups"][0]["groups"][0]["controls"]
    controls[0]["parts"][0]["id"] = "shared-statement"
    controls[1]["parts"][0]["id"] = "shared-statement"

    context = _prepare_plan_scope_context(
        grc_service,
        session_factory,
        selected_control_ids=["ac-1", "ac-2"],
        catalog_document=catalog,
    )
    service = context["ar_service"]

    statement_controls = AssessmentResultService._statement_controls(catalog)
    assert statement_controls.get("shared-statement") == {"ac-1": 1, "ac-2": 1}

    result = service.create_result(
        context["tenant_id"],
        context["actor"],
        context["system_id"],
        assessment_plan_id=context["plan"]["id"],
        assessment_plan_version_id=context["plan_version"]["id"],
        title="Ambiguous statement AR",
        description=None,
    )

    assert set(result["planned_control_ids"]) == {"ac-1", "ac-2"}
    planned_shared_statement_definitions = {
        control_id: count
        for control_id, count in statement_controls["shared-statement"].items()
        if control_id in set(result["planned_control_ids"])
    }
    assert planned_shared_statement_definitions == {"ac-1": 1, "ac-2": 1}

    assert all(
        option["statement_id"] != "shared-statement"
        for option in result["statement_options"]
    )

    with pytest.raises(InvalidAssessmentResult) as error:
        _update_result(service,
            context["tenant_id"],
            context["actor"],
            result["id"],
            title="Ambiguous statement AR",
            description=None,
            working_data={
                "reviewed_control_ids": ["ac-1"],
                "observations": [],
                "findings": [
                    {
                        "title": "Ambiguous target",
                        "description": "desc",
                        "target_type": "statement-id",
                        "target_id": "shared-statement",
                        "status": "satisfied",
                        "related_observation_ids": [],
                    }
                ],
                "start": None,
                "end": None,
            },
        )

    assert any(
        item["code"] == "ambiguous_statement_target"
        for item in error.value.diagnostics
    )


def test_assessment_result_rejects_ambiguous_catalog_objective_targets(
    grc_service, session_factory
) -> None:
    catalog = json.loads(FIXTURE_PATH.read_text())
    controls = catalog["catalog"]["groups"][0]["groups"][0]["controls"]
    controls[0].setdefault("parts", []).append(
        {
            "id": "shared-objective",
            "name": "objective",
            "prose": "Objective one.",
        }
    )
    controls[0]["objectives"] = [{"objective-id": "shared-objective"}]

    context = _prepare_plan_scope_context(
        grc_service,
        session_factory,
        selected_control_count=1,
        source_objectives=[
            {
                "objective_id": "shared-objective",
                "control_id": "ac-1",
            }
        ],
        catalog_document=catalog,
    )
    service = context["ar_service"]
    result = service.create_result(
        context["tenant_id"],
        context["actor"],
        context["system_id"],
        assessment_plan_id=context["plan"]["id"],
        assessment_plan_version_id=context["plan_version"]["id"],
        title="Ambiguous objective AR",
        description=None,
    )

    assert all(
        option["objective_id"] != "shared-objective"
        for option in result["objective_options"]
    )

    with pytest.raises(InvalidAssessmentResult) as error:
        _update_result(service,
            context["tenant_id"],
            context["actor"],
            result["id"],
            title="Ambiguous objective AR",
            description=None,
            working_data={
                "reviewed_control_ids": [context["controls"][0]],
                "observations": [],
                "findings": [
                    {
                        "title": "Ambiguous objective target",
                        "description": "desc",
                        "target_type": "objective-id",
                        "target_id": "shared-objective",
                        "status": "satisfied",
                        "related_observation_ids": [],
                    }
                ],
                "start": None,
                "end": None,
            },
        )

    assert any(
        item["code"] == "ambiguous_objective_target"
        for item in error.value.diagnostics
    )


def test_assessment_result_export_resolves_relevant_evidence_to_back_matter_resource(
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
        title="Evidence reference AR",
        description=None,
    )
    updated = _update_result(service,
        tenant_id,
        actor,
        result["id"],
        title="Evidence reference AR",
        description=None,
        working_data=_working_payload(
            control_id=control_id,
            observations=[
                {
                    "title": "Observation",
                    "description": "desc",
                    "methods": ["EXAMINE"],
                    "collected_at": "2026-11-20T00:30:00+00:00",
                    "subject_uuids": [str(subject_uuid)],
                    "evidence": [
                        {
                            "title": "Evidence",
                            "description": "desc",
                            "href": "https://example.test/evidence",
                        }
                    ],
                }
            ],
            findings=[
                {
                    "title": "Finding",
                    "description": "desc",
                    "target_type": "objective-id",
                    "target_id": "local-mfa-objective",
                    "status": "satisfied",
                    "related_observation_ids": [],
                }
            ],
        ),
    )
    observation_id = str(updated["observations"][0]["id"])
    finding_id = str(updated["findings"][0]["id"])
    updated = _update_result(service,
        tenant_id,
        actor,
        result["id"],
        title="Evidence reference AR",
        description=None,
        working_data=_working_payload(
            control_id=control_id,
            observations=updated["observations"],
            findings=[
                {
                    "id": finding_id,
                    "title": "Finding",
                    "description": "desc",
                    "target_type": "objective-id",
                    "target_id": "local-mfa-objective",
                    "status": "satisfied",
                    "related_observation_ids": [observation_id],
                }
            ],
        ),
    )
    evidence_id = str(updated["observations"][0]["evidence"][0]["id"])

    version = _publish_result(service, tenant_id, actor, result["id"])
    exported = service.export_version(tenant_id, result["id"], version["id"])
    resource_uuid = exported["assessment-results"]["back-matter"]["resources"][0]["uuid"]
    evidence_href = exported["assessment-results"]["results"][0]["observations"][0][
        "relevant-evidence"
    ][0]["href"]
    assert resource_uuid == evidence_id
    assert evidence_href == f"#{evidence_id}"


@pytest.mark.parametrize(
    "href",
    [
        "https://example.test/evidence",
        "http://example.test/evidence",
        "https://example.test./evidence",
        "https://example.test/report.pdf#page=12",
    ],
)
def test_assessment_result_accepts_http_and_https_evidence_urls(
    grc_service, session_factory, href: str
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
        title="Allowed URL AR",
        description=None,
    )
    updated = _update_result(service,
        tenant_id,
        actor,
        result["id"],
        title="Allowed URL AR",
        description=None,
        working_data=_working_payload(
            control_id=control_id,
            observations=[
                {
                    "title": "Observation",
                    "description": "desc",
                    "methods": ["EXAMINE"],
                    "collected_at": "2026-11-20T00:30:00+00:00",
                    "subject_uuids": [str(subject_uuid)],
                    "evidence": [{"title": "Evidence", "description": "desc", "href": href}],
                }
            ],
            findings=[
                {
                    "title": "Finding",
                    "description": "desc",
                    "target_type": "objective-id",
                    "target_id": "local-mfa-objective",
                    "status": "satisfied",
                    "related_observation_ids": [],
                }
            ],
        ),
    )
    assert updated["observations"][0]["evidence"][0]["href"] == href
    observation_id = str(updated["observations"][0]["id"])
    finding_id = str(updated["findings"][0]["id"])
    _update_result(service,
        tenant_id,
        actor,
        result["id"],
        title="Allowed URL AR",
        description=None,
        working_data=_working_payload(
            control_id=control_id,
            observations=updated["observations"],
            findings=[
                {
                    "id": finding_id,
                    "title": "Finding",
                    "description": "desc",
                    "target_type": "objective-id",
                    "target_id": "local-mfa-objective",
                    "status": "satisfied",
                    "related_observation_ids": [observation_id],
                }
            ],
        ),
    )
    validation = service.validate_result(tenant_id, result["id"])
    assert validation["valid"] is True
    version = _publish_result(service, tenant_id, actor, result["id"])
    assert version["created"] is True
    exported = service.export_version(tenant_id, result["id"], version["id"])
    assert (
        exported["assessment-results"]["back-matter"]["resources"][0]["rlinks"][0]["href"]
        == href
    )


@pytest.mark.parametrize(
    "href",
    [
        "javascript:alert(1)",
        "data:text/html,<b>x</b>",
        "vbscript:msgbox(1)",
        "file:///tmp/evidence.txt",
        "#resource-local",
        "/relative/path",
        "relative/path",
        "https://user:pass@example.test/evidence",
        "https://",
        " https://example.test/evidence",
        "https://example.test/evidence ",
        "https://example.test\\evidence",
        "https://example.test/evi dence",
        "https://example.test:abc/path",
        "https://example.test:99999/path",
        "https://%/",
        "https://exa|mple.test/path",
        "https://[bad",
        "https://example.test../path",
        "https://127.0.0.999/path",
        "https://example.test/%zz",
        "https://[v1.foo]/path",
    ],
)
def test_assessment_result_rejects_unsafe_or_ambiguous_evidence_urls(
    grc_service, session_factory, href: str
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
        title="Rejected URL AR",
        description=None,
    )
    with pytest.raises(InvalidAssessmentResult) as error:
        _update_result(service,
            tenant_id,
            actor,
            result["id"],
            title="Rejected URL AR",
            description=None,
            working_data=_working_payload(
                control_id=control_id,
                observations=[
                    {
                        "title": "Observation",
                        "description": "desc",
                        "methods": ["EXAMINE"],
                        "collected_at": "2026-11-20T00:30:00+00:00",
                        "subject_uuids": [str(subject_uuid)],
                        "evidence": [
                            {
                                "title": "Evidence",
                                "description": "desc",
                                "href": href,
                            }
                        ],
                    }
                ],
                findings=[],
            ),
        )
    assert any(item["code"] == "invalid_evidence_href" for item in error.value.diagnostics)
    assert any(
        item.get("path") == "$.observations[0].evidence[0].href"
        for item in error.value.diagnostics
        if item["code"] == "invalid_evidence_href"
    )


def test_assessment_result_distinguishes_fragment_only_from_fragmented_absolute_href() -> None:
    fragment_only_error = AssessmentResultService._validate_authored_evidence_href(
        "#resource-local"
    )
    absolute_fragment_error = AssessmentResultService._validate_authored_evidence_href(
        "https://example.test/path#fragment"
    )

    assert fragment_only_error is not None
    assert "fragment-only references" in fragment_only_error
    assert absolute_fragment_error is None


def _native_import_payload(
    *,
    tenant_id: UUID,
    plan_id: UUID,
    plan_version_id: UUID,
    control_id: str,
    subject_uuid: UUID,
    document_uuid: UUID | None = None,
    result_uuid: UUID | None = None,
    observation_uuid: UUID | None = None,
    evidence_uuid: UUID | None = None,
    finding_uuid: UUID | None = None,
    metadata_version: str = "automation-run-7",
    metadata_last_modified: str = "2026-11-19T10:15:00+00:00",
) -> dict[str, object]:
    document_uuid = document_uuid or uuid4()
    result_uuid = result_uuid or uuid4()
    observation_uuid = observation_uuid or uuid4()
    evidence_uuid = evidence_uuid or uuid4()
    finding_uuid = finding_uuid or uuid4()
    return {
        "assessment-results": {
            "uuid": str(document_uuid),
            "metadata": {
                "title": "Automated tenant assessment result import",
                "last-modified": metadata_last_modified,
                "version": metadata_version,
                "oscal-version": "1.2.1",
            },
            "import-ap": {
                "href": (
                    f"/api/v1/tenants/{tenant_id}/assessment-plans/{plan_id}/versions/"
                    f"{plan_version_id}/export"
                )
            },
            "results": [
                {
                    "uuid": str(result_uuid),
                    "title": "Automated execution findings",
                    "description": "Automated checks over privileged authentication controls.",
                    "reviewed-controls": {
                        "control-selections": [
                            {
                                "include-controls": [
                                    {
                                        "control-id": control_id,
                                    }
                                ]
                            }
                        ]
                    },
                    "start": "2026-11-19T09:00:00+00:00",
                    "end": "2026-11-19T09:30:00+00:00",
                    "observations": [
                        {
                            "uuid": str(observation_uuid),
                            "title": "Automated privileged login check",
                            "description": (
                                "Tool observed MFA challenge flow in production telemetry."
                            ),
                            "methods": ["TEST"],
                            "collected": "2026-11-19T09:12:00+00:00",
                            "subjects": [
                                {
                                    "type": "component",
                                    "subject-uuid": str(subject_uuid),
                                }
                            ],
                            "relevant-evidence": [
                                {
                                    "href": f"#{evidence_uuid}",
                                    "description": "Automated log extract.",
                                }
                            ],
                        }
                    ],
                    "findings": [
                        {
                            "uuid": str(finding_uuid),
                            "title": "MFA objective satisfied",
                            "description": "Automated check confirms objective coverage.",
                            "target": {
                                "type": "objective-id",
                                "target-id": "local-mfa-objective",
                                "status": {"state": "satisfied"},
                            },
                            "related-observations": [
                                {
                                    "observation-uuid": str(observation_uuid),
                                }
                            ],
                        }
                    ],
                }
            ],
            "back-matter": {
                "resources": [
                    {
                        "uuid": str(evidence_uuid),
                        "title": "Automated evidence artifact",
                        "description": "Automated log extract.",
                        "rlinks": [
                            {
                                "href": "https://example.test/evidence/mfa-automation-log.json",
                            }
                        ],
                    }
                ]
            },
        }
    }


def _set_overlong_result_title(payload: dict[str, object]) -> None:
    payload["assessment-results"]["results"][0]["title"] = "x" * 256


def _remove_observation_title(payload: dict[str, object]) -> None:
    payload["assessment-results"]["results"][0]["observations"][0].pop("title")


def _set_invalid_observation_methods(payload: dict[str, object]) -> None:
    payload["assessment-results"]["results"][0]["observations"][0]["methods"] = [
        "EXAMINE",
        "INTERVIEW",
        "TEST",
        "EXAMINE",
    ]


def test_assessment_result_import_maps_supported_native_oscal_subset_and_provenance(
    grc_service, session_factory
) -> None:
    (
        tenant_id,
        actor,
        _system_id,
        plan,
        plan_version,
        control_id,
        subject_uuid,
    ) = _prepare_plan_version(grc_service, session_factory)
    service = AssessmentResultService(lambda: session_factory.begin())
    payload = _native_import_payload(
        tenant_id=tenant_id,
        plan_id=plan["id"],
        plan_version_id=plan_version["id"],
        control_id=control_id,
        subject_uuid=subject_uuid,
    )

    imported, created = service.import_result(
        tenant_id,
        actor,
        assessment_plan_id=plan["id"],
        assessment_plan_version_id=plan_version["id"],
        document=payload,
    )

    assert created is True
    assert imported["concurrency_version"] == 1
    assert imported["assessment_plan_id"] == plan["id"]
    assert imported["assessment_plan_version_id"] == plan_version["id"]
    assert str(imported["observations"][0]["id"]) == (
        payload["assessment-results"]["results"][0]["observations"][0]["uuid"]
    )
    assert str(imported["findings"][0]["id"]) == (
        payload["assessment-results"]["results"][0]["findings"][0]["uuid"]
    )
    assert (
        str(imported["observations"][0]["evidence"][0]["id"])
        == payload["assessment-results"]["back-matter"]["resources"][0]["uuid"]
    )

    with session_factory.begin() as session:
        record = session.scalar(
            select(AssessmentResultRecord).where(
                AssessmentResultRecord.tenant_id == tenant_id,
                AssessmentResultRecord.id == imported["id"],
            )
        )
        assert record is not None
        assert record.source_document_uuid is not None
        assert record.source_content_sha256 is not None
        assert record.source_provenance is not None
        assert record.source_provenance["source_document_uuid"] == payload[
            "assessment-results"
        ]["uuid"]
        assert (
            record.source_provenance["source_metadata_title"]
            == payload["assessment-results"]["metadata"]["title"]
        )
        assert (
            record.source_provenance["source_result_uuid"]
            == payload["assessment-results"]["results"][0]["uuid"]
        )
        assert (
            record.source_provenance["source_metadata_version"]
            == payload["assessment-results"]["metadata"]["version"]
        )
        assert (
            record.source_provenance["source_metadata_last_modified"]
            == payload["assessment-results"]["metadata"]["last-modified"]
        )
        assert record.source_provenance["submitted_by"] == str(actor)


@pytest.mark.parametrize(
    "mutator,expected_path",
    [
        (_set_overlong_result_title, "$.title"),
        (_remove_observation_title, "$.observations.0.title"),
        (_set_invalid_observation_methods, "$.observations.0.methods"),
    ],
)
def test_assessment_result_import_rejects_invalid_mapped_working_state_without_persistence(
    grc_service,
    session_factory,
    mutator,
    expected_path: str,
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
    payload = _native_import_payload(
        tenant_id=tenant_id,
        plan_id=plan["id"],
        plan_version_id=plan_version["id"],
        control_id=control_id,
        subject_uuid=subject_uuid,
    )
    mutator(payload)

    with pytest.raises(InvalidAssessmentResult) as error:
        service.import_result(
            tenant_id,
            actor,
            assessment_plan_id=plan["id"],
            assessment_plan_version_id=plan_version["id"],
            document=payload,
        )

    assert any(item["code"] == "invalid_working_state" for item in error.value.diagnostics)
    assert any(item.get("path") == expected_path for item in error.value.diagnostics)
    assert service.list_results(tenant_id, system_id) == []


def test_assessment_result_import_rejects_invalid_assessment_interval_without_persistence(
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
    payload = _native_import_payload(
        tenant_id=tenant_id,
        plan_id=plan["id"],
        plan_version_id=plan_version["id"],
        control_id=control_id,
        subject_uuid=subject_uuid,
    )
    payload["assessment-results"]["results"][0]["start"] = "2026-11-19T10:00:00+00:00"
    payload["assessment-results"]["results"][0]["end"] = "2026-11-19T09:00:00+00:00"

    with pytest.raises(InvalidAssessmentResult) as error:
        service.import_result(
            tenant_id,
            actor,
            assessment_plan_id=plan["id"],
            assessment_plan_version_id=plan_version["id"],
            document=payload,
        )

    assert any(item["code"] == "invalid_working_state" for item in error.value.diagnostics)
    assert service.list_results(tenant_id, system_id) == []


def test_assessment_result_import_is_idempotent_for_identical_replay(
    grc_service, session_factory
) -> None:
    (
        tenant_id,
        actor,
        _system_id,
        plan,
        plan_version,
        control_id,
        subject_uuid,
    ) = _prepare_plan_version(grc_service, session_factory)
    service = AssessmentResultService(lambda: session_factory.begin())
    payload = _native_import_payload(
        tenant_id=tenant_id,
        plan_id=plan["id"],
        plan_version_id=plan_version["id"],
        control_id=control_id,
        subject_uuid=subject_uuid,
    )

    first, first_created = service.import_result(
        tenant_id,
        actor,
        assessment_plan_id=plan["id"],
        assessment_plan_version_id=plan_version["id"],
        document=payload,
    )
    replay, replay_created = service.import_result(
        tenant_id,
        actor,
        assessment_plan_id=plan["id"],
        assessment_plan_version_id=plan_version["id"],
        document=payload,
    )

    assert first_created is True
    assert replay_created is False
    assert replay["id"] == first["id"]


def test_assessment_result_import_rejects_conflicting_reuse_of_document_uuid(
    grc_service, session_factory
) -> None:
    (
        tenant_id,
        actor,
        _system_id,
        plan,
        plan_version,
        control_id,
        subject_uuid,
    ) = _prepare_plan_version(grc_service, session_factory)
    service = AssessmentResultService(lambda: session_factory.begin())
    source_uuid = uuid4()
    first_payload = _native_import_payload(
        tenant_id=tenant_id,
        plan_id=plan["id"],
        plan_version_id=plan_version["id"],
        control_id=control_id,
        subject_uuid=subject_uuid,
        document_uuid=source_uuid,
    )
    conflicting_payload = _native_import_payload(
        tenant_id=tenant_id,
        plan_id=plan["id"],
        plan_version_id=plan_version["id"],
        control_id=control_id,
        subject_uuid=subject_uuid,
        document_uuid=source_uuid,
        metadata_version="automation-run-8",
    )

    service.import_result(
        tenant_id,
        actor,
        assessment_plan_id=plan["id"],
        assessment_plan_version_id=plan_version["id"],
        document=first_payload,
    )

    with pytest.raises(AssessmentResultImportConflict) as error:
        service.import_result(
            tenant_id,
            actor,
            assessment_plan_id=plan["id"],
            assessment_plan_version_id=plan_version["id"],
            document=conflicting_payload,
        )
    assert error.value.reason == "content_mismatch"
    assert error.value.source_document_uuid == source_uuid


def test_assessment_result_import_rejects_context_mismatch_for_reused_document_uuid(
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
    source_uuid = uuid4()
    first_payload = _native_import_payload(
        tenant_id=tenant_id,
        plan_id=plan["id"],
        plan_version_id=plan_version["id"],
        control_id=control_id,
        subject_uuid=subject_uuid,
        document_uuid=source_uuid,
    )
    service.import_result(
        tenant_id,
        actor,
        assessment_plan_id=plan["id"],
        assessment_plan_version_id=plan_version["id"],
        document=first_payload,
    )

    ap_service = AssessmentPlanService(lambda: session_factory.begin())
    ap_service.update_plan(
        tenant_id,
        actor,
        plan["id"],
        expected_version=_expected_version(ap_service, tenant_id, plan["id"]),
        title=f"{plan['title']} v2",
        description="Updated title to create a distinct historical AP version context.",
        working_data={
            "control_ids": [control_id],
            "source_objectives": [],
            "local_objectives": [
                {
                    "objective_id": "local-mfa-objective",
                    "control_id": control_id,
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
    second_plan_version = ap_service.create_version(
        tenant_id,
        actor,
        plan["id"],
        expected_version=_expected_version(ap_service, tenant_id, plan["id"]),
    )

    mismatch_payload = _native_import_payload(
        tenant_id=tenant_id,
        plan_id=plan["id"],
        plan_version_id=second_plan_version["id"],
        control_id=control_id,
        subject_uuid=subject_uuid,
        document_uuid=source_uuid,
    )

    with pytest.raises(AssessmentResultImportConflict) as error:
        service.import_result(
            tenant_id,
            actor,
            assessment_plan_id=plan["id"],
            assessment_plan_version_id=second_plan_version["id"],
            document=mismatch_payload,
        )
    assert error.value.reason == "assessment_context_mismatch"

    listed = service.list_results(tenant_id, system_id)
    assert len(listed) == 1


def test_assessment_result_import_rejects_unsupported_fields_without_persistence(
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
    payload = _native_import_payload(
        tenant_id=tenant_id,
        plan_id=plan["id"],
        plan_version_id=plan_version["id"],
        control_id=control_id,
        subject_uuid=subject_uuid,
    )
    payload["assessment-results"]["results"][0]["observations"][0]["remarks"] = "unsupported"

    with pytest.raises(InvalidAssessmentResult) as error:
        service.import_result(
            tenant_id,
            actor,
            assessment_plan_id=plan["id"],
            assessment_plan_version_id=plan_version["id"],
            document=payload,
        )
    assert any(item["code"] == "unsupported_import_field" for item in error.value.diagnostics)
    assert service.list_results(tenant_id, system_id) == []


def test_assessment_result_import_rejects_mismatched_import_ap_without_partial_persistence(
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
    payload = _native_import_payload(
        tenant_id=tenant_id,
        plan_id=plan["id"],
        plan_version_id=plan_version["id"],
        control_id=control_id,
        subject_uuid=subject_uuid,
    )
    payload["assessment-results"]["import-ap"]["href"] = (
        "/api/v1/tenants/other/assessment-plans/x/versions/y/export"
    )

    with pytest.raises(InvalidAssessmentResult) as error:
        service.import_result(
            tenant_id,
            actor,
            assessment_plan_id=plan["id"],
            assessment_plan_version_id=plan_version["id"],
            document=payload,
        )
    assert any(item["code"] in {"oscal_model", "oscal_schema"} for item in error.value.diagnostics)
    assert service.list_results(tenant_id, system_id) == []


def test_assessment_result_import_is_concurrency_safe_for_duplicate_submissions(
    grc_service, session_factory, monkeypatch
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
    payload = _native_import_payload(
        tenant_id=tenant_id,
        plan_id=plan["id"],
        plan_version_id=plan_version["id"],
        control_id=control_id,
        subject_uuid=subject_uuid,
    )
    service = AssessmentResultService(lambda: session_factory.begin())

    barrier = threading.Barrier(3)
    insert_flush_count = {"value": 0}
    unique_recovery_used = threading.Event()
    second_insert_flushed = threading.Event()
    flush_lock = threading.Lock()
    first_flush_waiting = {"value": False}

    target_source_uuid = UUID(payload["assessment-results"]["uuid"])

    original_flush = Session.flush
    original_conflict_probe = AssessmentResultService._is_source_document_constraint_violation

    def _gated_flush(session: Session, *args, **kwargs):
        relevant_insert = any(
            isinstance(item, AssessmentResultRecord)
            and item.source_document_uuid == target_source_uuid
            for item in session.new
        )
        if not relevant_insert:
            return original_flush(session, *args, **kwargs)

        with flush_lock:
            insert_flush_count["value"] += 1
            if not first_flush_waiting["value"]:
                first_flush_waiting["value"] = True
                is_first = True
            else:
                is_first = False

        if is_first:
            assert second_insert_flushed.wait(timeout=5)
            return original_flush(session, *args, **kwargs)

        try:
            return original_flush(session, *args, **kwargs)
        finally:
            second_insert_flushed.set()

    def _tracking_conflict_probe(error):
        matched = original_conflict_probe(error)
        if matched:
            unique_recovery_used.set()
        return matched

    monkeypatch.setattr(Session, "flush", _gated_flush)
    monkeypatch.setattr(
        AssessmentResultService,
        "_is_source_document_constraint_violation",
        staticmethod(_tracking_conflict_probe),
    )

    def _submit_once() -> tuple[UUID, bool]:
        concurrent_service = AssessmentResultService(lambda: session_factory.begin())
        barrier.wait(timeout=5)
        result, created = concurrent_service.import_result(
            tenant_id,
            actor,
            assessment_plan_id=plan["id"],
            assessment_plan_version_id=plan_version["id"],
            document=payload,
        )
        return result["id"], created

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(_submit_once)
        second = executor.submit(_submit_once)
        barrier.wait(timeout=5)
        first_result = first.result()
        second_result = second.result()

    assert {first_result[0], second_result[0]} <= {
        service.list_results(tenant_id, system_id)[0]["id"]
    }
    assert {first_result[1], second_result[1]} == {True, False}
    assert insert_flush_count["value"] >= 2
    assert unique_recovery_used.is_set()
    assert len(service.list_results(tenant_id, system_id)) == 1


def test_assessment_result_import_supports_publication_and_native_export(
    grc_service, session_factory
) -> None:
    (
        tenant_id,
        actor,
        _system_id,
        plan,
        plan_version,
        control_id,
        subject_uuid,
    ) = _prepare_plan_version(grc_service, session_factory)
    service = AssessmentResultService(lambda: session_factory.begin())
    payload = _native_import_payload(
        tenant_id=tenant_id,
        plan_id=plan["id"],
        plan_version_id=plan_version["id"],
        control_id=control_id,
        subject_uuid=subject_uuid,
    )

    imported, created = service.import_result(
        tenant_id,
        actor,
        assessment_plan_id=plan["id"],
        assessment_plan_version_id=plan_version["id"],
        document=payload,
    )
    assert created is True

    version = _publish_result(
        service,
        tenant_id,
        actor,
        imported["id"],
        expected_version=imported["concurrency_version"],
    )
    assert version["created"] is True
    exported = service.export_version(tenant_id, imported["id"], version["id"])
    exported_result = exported["assessment-results"]["results"][0]
    exported_observation = exported_result["observations"][0]
    exported_finding = exported_result["findings"][0]
    exported_resource = exported["assessment-results"]["back-matter"]["resources"][0]

    assert exported["assessment-results"]["import-ap"]["href"].endswith(
        f"/{plan_version['id']}/export"
    )
    assert exported_observation["uuid"] == (
        payload["assessment-results"]["results"][0]["observations"][0]["uuid"]
    )
    assert exported_finding["uuid"] == (
        payload["assessment-results"]["results"][0]["findings"][0]["uuid"]
    )
    assert exported_resource["uuid"] == (
        payload["assessment-results"]["back-matter"]["resources"][0]["uuid"]
    )


def test_assessment_result_import_replay_after_edit_or_publication_preserves_existing_state(
    grc_service, session_factory
) -> None:
    (
        tenant_id,
        actor,
        _system_id,
        plan,
        plan_version,
        control_id,
        subject_uuid,
    ) = _prepare_plan_version(grc_service, session_factory)
    service = AssessmentResultService(lambda: session_factory.begin())
    payload = _native_import_payload(
        tenant_id=tenant_id,
        plan_id=plan["id"],
        plan_version_id=plan_version["id"],
        control_id=control_id,
        subject_uuid=subject_uuid,
    )

    imported, created = service.import_result(
        tenant_id,
        actor,
        assessment_plan_id=plan["id"],
        assessment_plan_version_id=plan_version["id"],
        document=payload,
    )
    assert created is True

    edited = _update_result(
        service,
        tenant_id,
        actor,
        imported["id"],
        title="Edited after import",
        description=imported["description"],
        working_data={
            "reviewed_control_ids": imported["reviewed_control_ids"],
            "observations": imported["observations"],
            "findings": imported["findings"],
            "start": imported["start"],
            "end": imported["end"],
        },
    )
    replay_after_edit, created_after_edit = service.import_result(
        tenant_id,
        actor,
        assessment_plan_id=plan["id"],
        assessment_plan_version_id=plan_version["id"],
        document=payload,
    )
    assert created_after_edit is False
    assert replay_after_edit["id"] == imported["id"]
    assert replay_after_edit["title"] == "Edited after import"
    assert replay_after_edit["concurrency_version"] == edited["concurrency_version"]

    published = _publish_result(
        service,
        tenant_id,
        actor,
        imported["id"],
        expected_version=edited["concurrency_version"],
    )
    assert published["created"] is True
    versions_before_replay = service.list_versions(tenant_id, imported["id"])

    replay_after_publish, created_after_publish = service.import_result(
        tenant_id,
        actor,
        assessment_plan_id=plan["id"],
        assessment_plan_version_id=plan_version["id"],
        document=payload,
    )
    assert created_after_publish is False
    assert replay_after_publish["id"] == imported["id"]
    assert replay_after_publish["title"] == "Edited after import"
    assert service.list_versions(tenant_id, imported["id"]) == versions_before_replay







