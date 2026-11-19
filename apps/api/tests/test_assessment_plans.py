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
from sqlalchemy.orm.exc import StaleDataError

from app.application.assessment_plans import (
    AssessmentPlanService,
    InvalidAssessmentPlan,
    StaleAssessmentPlanUpdate,
)
from app.application.implementations import ImplementationService
from app.application.system_security_plans import SystemSecurityPlanService
from app.domain.catalogs.models import CatalogOriginType
from app.domain.implementations import (
    ImplementationInformation,
    ImplementationStatus,
    OscalImplementationStatus,
)
from app.persistence.identity import SQLIdentityRepository, SQLMembershipRepository
from app.persistence.models import (
    AssessmentPlanRecord,
    CatalogControlIndexRecord,
)

pytestmark = pytest.mark.integration
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "oscal_catalog.json"
ARCH_FIXTURE_PATH = (
    Path(__file__).parents[3] / "examples" / "catalogs" / "Grundschutz++-resolved_catalog.json"
)


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


def _prepare_ssp_version(
    grc_service,
    session_factory,
    *,
    fixture_path: Path = FIXTURE_PATH,
    component_type: str = "service",
) -> tuple[UUID, UUID, UUID, UUID, UUID, list[str]]:
    tenant = grc_service.create_tenant("AP tenant", f"ap-{uuid4().hex}")
    actor = _actor(session_factory, tenant.id)
    catalog = grc_service.create_catalog(tenant.id, "Security baseline", CatalogOriginType.CUSTOM)
    catalog_document = json.loads(fixture_path.read_text())
    revision = grc_service.create_draft_catalog_revision(tenant.id, catalog.id, catalog_document)

    with session_factory.begin() as session:
        baseline_controls = session.scalars(
            select(CatalogControlIndexRecord.oscal_control_id)
            .where(
                CatalogControlIndexRecord.tenant_id == tenant.id,
                CatalogControlIndexRecord.catalog_revision_id == revision.id,
            )
            .order_by(CatalogControlIndexRecord.oscal_control_id)
        ).all()

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
        component_type=component_type,
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
        baseline_controls[0],
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
        plan["id"],
        implementation.id,
        component["id"],
        expected_version=plan["concurrency_version"],
    )
    plan["concurrency_version"] = included["concurrency_version"]
    version = ssp_service.create_version(
        tenant.id,
        actor,
        plan["id"],
        expected_version=plan["concurrency_version"],
    )
    component_uuid = component["oscal_component_uuid"]
    subject_uuid = component_uuid if isinstance(component_uuid, UUID) else UUID(component_uuid)
    return (
        tenant.id,
        actor,
        system["id"],
        version["id"],
        subject_uuid,
        baseline_controls,
    )


def _expected_version(service: AssessmentPlanService, tenant_id: UUID, plan_id: UUID) -> int:
    return int(service.get_plan(tenant_id, plan_id)["concurrency_version"])


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


def test_assessment_plan_lifecycle_uses_pinned_ssp_snapshot(grc_service, session_factory) -> None:
    (
        tenant_id,
        actor,
        system_id,
        ssp_version_id,
        subject_uuid,
        _baseline_controls,
    ) = _prepare_ssp_version(grc_service, session_factory)
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
        expected_version=_expected_version(service, tenant_id, plan["id"]),
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

    first = service.create_version(
        tenant_id,
        actor,
        plan["id"],
        expected_version=_expected_version(service, tenant_id, plan["id"]),
    )
    assert first["created"]
    assert first["oscal_version"] == "1.2.1"
    exported = service.export_version(tenant_id, plan["id"], first["id"])
    assert exported["assessment-plan"]["import-ssp"]["href"].endswith(
        f"/{ssp_version_id}/export"
    )

    unchanged = service.create_version(
        tenant_id,
        actor,
        plan["id"],
        expected_version=_expected_version(service, tenant_id, plan["id"]),
    )
    assert unchanged["created"] is False
    assert unchanged["id"] == first["id"]


def test_assessment_plan_rejects_controls_or_subjects_outside_pinned_snapshot(
    grc_service, session_factory
) -> None:
    (
        tenant_id,
        actor,
        system_id,
        ssp_version_id,
        _subject_uuid,
        _baseline_controls,
    ) = _prepare_ssp_version(grc_service, session_factory)
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
            expected_version=_expected_version(service, tenant_id, plan["id"]),
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


def test_assessment_plan_minimal_scope_validates_repeatedly_without_state_changes(
    grc_service, session_factory
) -> None:
    (
        tenant_id,
        actor,
        system_id,
        ssp_version_id,
        subject_uuid,
        baseline_controls,
    ) = _prepare_ssp_version(
        grc_service,
        session_factory,
        fixture_path=ARCH_FIXTURE_PATH,
        component_type="region",
    )
    service = AssessmentPlanService(lambda: session_factory.begin())
    selected_controls = baseline_controls[:13]

    plan = service.create_plan(
        tenant_id,
        actor,
        system_id,
        ssp_version_id=ssp_version_id,
        title="ARCH Minimal AP",
        description="Minimal AP with immutable SSP 1.2.3 reference.",
    )

    service.update_plan(
        tenant_id,
        actor,
        plan["id"],
        expected_version=_expected_version(service, tenant_id, plan["id"]),
        title="ARCH Minimal AP",
        description="Minimal AP with immutable SSP 1.2.3 reference.",
        working_data={
            "control_ids": selected_controls,
            "source_objectives": [],
            "local_objectives": [],
            "subject_uuids": [str(subject_uuid)],
            "activities": [],
            "tasks": [],
            "roles": [],
            "parties": [],
            "terms": None,
        },
    )

    first_validation = service.validate_plan(tenant_id, plan["id"])
    second_validation = service.validate_plan(tenant_id, plan["id"])
    assert first_validation["valid"] is True
    assert second_validation["valid"] is True
    assert first_validation["oscal_candidate"]["assessment-plan"]["metadata"]["version"] == "draft"

    first_version = service.create_version(
        tenant_id,
        actor,
        plan["id"],
        expected_version=_expected_version(service, tenant_id, plan["id"]),
    )
    assert first_version["created"] is True
    assert first_version["oscal_version"] == "1.2.1"

    exported = service.export_version(tenant_id, plan["id"], first_version["id"])
    metadata = exported["assessment-plan"]["metadata"]
    assert metadata["version"] == first_version["document_version"]
    assert metadata["version"] != "draft"
    assert exported["assessment-plan"]["import-ssp"]["href"].endswith(
        f"/{ssp_version_id}/export"
    )

    reused = service.create_version(
        tenant_id,
        actor,
        plan["id"],
        expected_version=_expected_version(service, tenant_id, plan["id"]),
    )
    assert reused["created"] is False
    assert reused["id"] == first_version["id"]


def test_assessment_plan_local_objectives_support_same_control_and_reference_integrity(
    grc_service, session_factory
) -> None:
    (
        tenant_id,
        actor,
        system_id,
        ssp_version_id,
        subject_uuid,
        _baseline_controls,
    ) = _prepare_ssp_version(grc_service, session_factory)
    service = AssessmentPlanService(lambda: session_factory.begin())

    plan = service.create_plan(
        tenant_id,
        actor,
        system_id,
        ssp_version_id=ssp_version_id,
        title="Objective Integrity AP",
        description=None,
    )

    updated = service.update_plan(
        tenant_id,
        actor,
        plan["id"],
        expected_version=_expected_version(service, tenant_id, plan["id"]),
        title="Objective Integrity AP",
        description=None,
        working_data={
            "control_ids": ["ac-1"],
            "source_objectives": [],
            "local_objectives": [
                {
                    "objective_id": "local-ac-1-1",
                    "control_id": "ac-1",
                    "description": "First local objective.",
                    "methods": ["EXAMINE"],
                },
                {
                    "objective_id": "local-ac-1-2",
                    "control_id": "ac-1",
                    "description": "Second local objective.",
                    "methods": ["TEST"],
                },
            ],
            "subject_uuids": [str(subject_uuid)],
            "activities": [
                {
                    "title": "Assess objective one",
                    "description": "Activity uses first local objective.",
                    "methods": ["EXAMINE"],
                    "steps": [],
                    "control_ids": ["ac-1"],
                    "objective_ids": ["local-ac-1-1"],
                    "planned_evidence": None,
                }
            ],
            "tasks": [],
            "roles": [],
            "parties": [],
            "terms": None,
        },
    )
    assert len(updated["local_objectives"]) == 2
    assert service.validate_plan(tenant_id, plan["id"])["valid"] is True

    exported = service.export_version(
        tenant_id,
        plan["id"],
        service.create_version(
            tenant_id,
            actor,
            plan["id"],
            expected_version=_expected_version(service, tenant_id, plan["id"]),
        )["id"],
    )
    local_defs = exported["assessment-plan"]["local-definitions"]["objectives-and-methods"]
    assert all(item["control-id"] == "ac-1" for item in local_defs)
    assert {item["parts"][0]["id"] for item in local_defs} == {"local-ac-1-1", "local-ac-1-2"}


def test_assessment_plan_rejects_invalid_objective_references_and_conflicts(
    grc_service, session_factory
) -> None:
    (
        tenant_id,
        actor,
        system_id,
        ssp_version_id,
        subject_uuid,
        _baseline_controls,
    ) = _prepare_ssp_version(grc_service, session_factory)
    service = AssessmentPlanService(lambda: session_factory.begin())
    plan = service.create_plan(
        tenant_id,
        actor,
        system_id,
        ssp_version_id=ssp_version_id,
        title="Diagnostics AP",
        description=None,
    )

    with pytest.raises(InvalidAssessmentPlan) as error:
        service.update_plan(
            tenant_id,
            actor,
            plan["id"],
            expected_version=_expected_version(service, tenant_id, plan["id"]),
            title="Diagnostics AP",
            description=None,
            working_data={
                "control_ids": ["ac-1"],
                "source_objectives": [],
                "local_objectives": [
                    {
                        "objective_id": "local-ac-1-1",
                        "control_id": "ac-1",
                        "description": "desc",
                        "methods": ["EXAMINE"],
                    }
                ],
                "subject_uuids": [str(subject_uuid)],
                "activities": [
                    {
                        "title": "Bad objective reference",
                        "description": "This references a missing objective id.",
                        "methods": ["EXAMINE"],
                        "steps": [],
                        "control_ids": ["ac-1"],
                        "objective_ids": ["missing-local-objective"],
                        "planned_evidence": None,
                    }
                ],
                "tasks": [],
                "roles": [],
                "parties": [],
                "terms": None,
            },
        )
    diagnostics = error.value.diagnostics
    assert any(item["code"] == "activity_unknown_objective" for item in diagnostics)

    with pytest.raises(InvalidAssessmentPlan) as conflict_error:
        service.update_plan(
            tenant_id,
            actor,
            plan["id"],
            expected_version=_expected_version(service, tenant_id, plan["id"]),
            title="Diagnostics AP",
            description=None,
            working_data={
                "control_ids": ["ac-1"],
                "source_objectives": [{"objective_id": "shared-id", "control_id": "ac-1"}],
                "local_objectives": [
                    {
                        "objective_id": "shared-id",
                        "control_id": "ac-1",
                        "description": "conflict",
                        "methods": ["EXAMINE"],
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
    assert any(item["code"] == "objective_id_conflict" for item in conflict_error.value.diagnostics)


def test_assessment_plan_update_rejects_stale_token_under_concurrent_transactions(
    grc_service, session_factory, monkeypatch
) -> None:
    tenant_id, actor, system_id, ssp_version_id, subject_uuid, _ = _prepare_ssp_version(
        grc_service, session_factory
    )
    service = AssessmentPlanService(lambda: session_factory.begin())
    plan = service.create_plan(
        tenant_id,
        actor,
        system_id,
        ssp_version_id=ssp_version_id,
        title="Concurrent AP",
        description="Concurrency check",
    )
    token = _expected_version(service, tenant_id, plan["id"])
    release = threading.Barrier(3)
    winner_holding_lock = threading.Event()
    gate_release = threading.Event()
    state_lock = threading.Lock()
    backend_pids: dict[str, int] = {}
    winner_pid: dict[str, int | None] = {"value": None}
    original_get_plan = AssessmentPlanService._get_plan

    def _gated_get_plan(session, tenant_id, plan_id, *, lock=False):
        loaded = original_get_plan(session, tenant_id, plan_id, lock=lock)
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

    monkeypatch.setattr(AssessmentPlanService, "_get_plan", staticmethod(_gated_get_plan))

    def _attempt_update(title: str, worker: str) -> str:
        with session_factory.begin() as thread_session:
            with state_lock:
                backend_pids[worker] = _backend_pid(thread_session)
            concurrent_service = AssessmentPlanService(lambda: _bound_scope(thread_session))
            release.wait(timeout=5)
            concurrent_service.update_plan(
                tenant_id,
                actor,
                plan["id"],
                expected_version=token,
                title=title,
                description="Concurrency check",
                working_data={
                    "control_ids": ["ac-1"],
                    "source_objectives": [],
                    "local_objectives": [],
                    "subject_uuids": [str(subject_uuid)],
                    "activities": [],
                    "tasks": [],
                    "roles": [],
                    "parties": [],
                    "terms": None,
                },
            )
            return title

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(_attempt_update, "Concurrent AP A", "a"),
            executor.submit(_attempt_update, "Concurrent AP B", "b"),
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

    results = []
    stale = []
    for future in futures:
        try:
            results.append(future.result())
        except StaleAssessmentPlanUpdate as error:
            stale.append(error)

    assert len(results) == 1
    assert len(stale) == 1
    assert stale[0].expected_version == token
    assert stale[0].current_version == token + 1

    persisted = service.get_plan(tenant_id, plan["id"])
    assert persisted["concurrency_version"] == token + 1
    assert persisted["title"] == results[0]


def test_assessment_plan_publish_rejects_stale_token_under_concurrent_transactions(
    grc_service, session_factory, monkeypatch
) -> None:
    tenant_id, actor, system_id, ssp_version_id, subject_uuid, _ = _prepare_ssp_version(
        grc_service, session_factory
    )
    service = AssessmentPlanService(lambda: session_factory.begin())
    plan = service.create_plan(
        tenant_id,
        actor,
        system_id,
        ssp_version_id=ssp_version_id,
        title="Concurrent AP publish",
        description="Concurrency check",
    )
    updated = service.update_plan(
        tenant_id,
        actor,
        plan["id"],
        expected_version=_expected_version(service, tenant_id, plan["id"]),
        title=plan["title"],
        description=plan["description"],
        working_data={
            "control_ids": ["ac-1"],
            "source_objectives": [],
            "local_objectives": [],
            "subject_uuids": [str(subject_uuid)],
            "activities": [],
            "tasks": [],
            "roles": [],
            "parties": [],
            "terms": None,
        },
    )
    token = updated["concurrency_version"]
    release = threading.Barrier(3)
    winner_holding_lock = threading.Event()
    gate_release = threading.Event()
    state_lock = threading.Lock()
    backend_pids: dict[str, int] = {}
    winner_pid: dict[str, int | None] = {"value": None}
    original_get_plan = AssessmentPlanService._get_plan

    def _gated_get_plan(session, tenant_id, plan_id, *, lock=False):
        loaded = original_get_plan(session, tenant_id, plan_id, lock=lock)
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

    monkeypatch.setattr(AssessmentPlanService, "_get_plan", staticmethod(_gated_get_plan))

    def _attempt_publish(worker: str) -> dict[str, object]:
        with session_factory.begin() as thread_session:
            with state_lock:
                backend_pids[worker] = _backend_pid(thread_session)
            concurrent_service = AssessmentPlanService(lambda: _bound_scope(thread_session))
            release.wait(timeout=5)
            return concurrent_service.create_version(
                tenant_id,
                actor,
                plan["id"],
                expected_version=token,
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(_attempt_publish, "a"),
            executor.submit(_attempt_publish, "b"),
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

    published = []
    stale = []
    for future in futures:
        try:
            published.append(future.result())
        except StaleAssessmentPlanUpdate as error:
            stale.append(error)

    assert len(published) == 1
    assert published[0]["created"] is True
    assert len(stale) == 1
    assert stale[0].expected_version == token
    assert stale[0].current_version == token + 1

    versions = service.list_versions(tenant_id, plan["id"])
    assert len(versions) == 1
    assert versions[0]["id"] == published[0]["id"]

    persisted = service.get_plan(tenant_id, plan["id"])
    assert persisted["concurrency_version"] == token + 1


def test_assessment_plan_update_translates_mapper_stale_error(
    grc_service, session_factory, monkeypatch
) -> None:
    tenant_id, actor, system_id, ssp_version_id, subject_uuid, _ = _prepare_ssp_version(
        grc_service, session_factory
    )
    service = AssessmentPlanService(lambda: session_factory.begin())
    created = service.create_plan(
        tenant_id,
        actor,
        system_id,
        ssp_version_id=ssp_version_id,
        title="Forced mapper stale",
        description=None,
    )
    token = created["concurrency_version"]

    original_get_plan = AssessmentPlanService._get_plan
    loaded_version_unchanged = {"value": False}

    def _stale_mapper_version_get_plan(session, tenant_id, plan_id, *, lock=False):
        loaded = original_get_plan(session, tenant_id, plan_id, lock=lock)
        if lock:
            loaded_version = int(loaded.concurrency_version)
            session.execute(
                update(AssessmentPlanRecord)
                .where(
                    AssessmentPlanRecord.tenant_id == tenant_id,
                    AssessmentPlanRecord.id == plan_id,
                )
                .values(
                    concurrency_version=AssessmentPlanRecord.concurrency_version + 1,
                )
                .execution_options(synchronize_session=False)
            )
            loaded_version_unchanged["value"] = int(loaded.concurrency_version) == loaded_version
        return loaded

    monkeypatch.setattr(
        AssessmentPlanService,
        "_get_plan",
        staticmethod(_stale_mapper_version_get_plan),
    )

    with pytest.raises(StaleAssessmentPlanUpdate) as error:
        service.update_plan(
            tenant_id,
            actor,
            created["id"],
            expected_version=token,
            title="Forced mapper stale",
            description=None,
            working_data={
                "control_ids": ["ac-1"],
                "source_objectives": [],
                "local_objectives": [],
                "subject_uuids": [str(subject_uuid)],
                "activities": [],
                "tasks": [],
                "roles": [],
                "parties": [],
                "terms": None,
            },
        )

    persisted = service.get_plan(tenant_id, created["id"])
    assert loaded_version_unchanged["value"] is True
    assert isinstance(error.value.__cause__, StaleDataError)
    assert error.value.expected_version == token
    assert error.value.current_version == token
    assert persisted["concurrency_version"] == token
    assert persisted["title"] == created["title"]


def test_assessment_plan_publish_translates_mapper_stale_error(
    grc_service, session_factory, monkeypatch
) -> None:
    tenant_id, actor, system_id, ssp_version_id, subject_uuid, _ = _prepare_ssp_version(
        grc_service, session_factory
    )
    service = AssessmentPlanService(lambda: session_factory.begin())
    plan = service.create_plan(
        tenant_id,
        actor,
        system_id,
        ssp_version_id=ssp_version_id,
        title="Forced mapper stale publish",
        description=None,
    )
    updated = service.update_plan(
        tenant_id,
        actor,
        plan["id"],
        expected_version=plan["concurrency_version"],
        title=plan["title"],
        description=plan["description"],
        working_data={
            "control_ids": ["ac-1"],
            "source_objectives": [],
            "local_objectives": [],
            "subject_uuids": [str(subject_uuid)],
            "activities": [],
            "tasks": [],
            "roles": [],
            "parties": [],
            "terms": None,
        },
    )
    token = updated["concurrency_version"]
    assert service.list_versions(tenant_id, plan["id"]) == []

    original_get_plan = AssessmentPlanService._get_plan
    loaded_version_unchanged = {"value": False}

    def _stale_mapper_version_get_plan(session, tenant_id, plan_id, *, lock=False):
        loaded = original_get_plan(session, tenant_id, plan_id, lock=lock)
        if lock:
            loaded_version = int(loaded.concurrency_version)
            session.execute(
                update(AssessmentPlanRecord)
                .where(
                    AssessmentPlanRecord.tenant_id == tenant_id,
                    AssessmentPlanRecord.id == plan_id,
                )
                .values(
                    concurrency_version=AssessmentPlanRecord.concurrency_version + 1,
                )
                .execution_options(synchronize_session=False)
            )
            loaded_version_unchanged["value"] = int(loaded.concurrency_version) == loaded_version
        return loaded

    monkeypatch.setattr(
        AssessmentPlanService,
        "_get_plan",
        staticmethod(_stale_mapper_version_get_plan),
    )

    with pytest.raises(StaleAssessmentPlanUpdate) as error:
        service.create_version(
            tenant_id,
            actor,
            plan["id"],
            expected_version=token,
        )

    assert loaded_version_unchanged["value"] is True
    assert isinstance(error.value.__cause__, StaleDataError)
    assert error.value.expected_version == token
    assert error.value.current_version == token
    assert service.list_versions(tenant_id, plan["id"]) == []
    assert service.get_plan(tenant_id, plan["id"])["concurrency_version"] == token






