# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.orm.exc import StaleDataError

import app.application.implementations as implementation_module
import app.application.system_security_plans as ssp_module
from app.application.implementations import ImplementationService, StaleImplementationUpdate
from app.application.system_security_plans import (
    StaleSystemSecurityPlanUpdate,
    SystemSecurityPlanService,
)
from app.domain.catalogs.models import CatalogOriginType
from app.domain.implementations import (
    ImplementationInformation,
    ImplementationStatus,
    OscalImplementationStatus,
    Responsibility,
    ResponsibilityKind,
)
from app.persistence.identity import SQLIdentityRepository, SQLMembershipRepository
from app.persistence.models import (
    CatalogControlIndexRecord,
    ControlImplementationRecord,
    ImplementationResponsibilityRecord,
    SystemSecurityPlanImplementationRecord,
    SystemSecurityPlanRecord,
)

pytestmark = pytest.mark.integration
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "oscal_catalog.json"


@contextmanager
def _bound_scope(session):
    yield session


def _actor(session_factory, tenant_id: UUID) -> UUID:
    with session_factory.begin() as session:
        identity = SQLIdentityRepository(session).get_or_create(
            issuer="https://issuer.example.test",
            subject=f"ssp-concurrency-author-{uuid4()}",
            display_name="SSP Concurrency Author",
            email=None,
        )
        SQLMembershipRepository(session).assign(
            tenant_id=tenant_id,
            user_id=identity.id,
            role="catalog_editor",
            status="active",
        )
        return identity.id


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


def _prepare_ssp_context(grc_service, session_factory):
    tenant = grc_service.create_tenant("SSP concurrency tenant", f"ssp-concurrency-{uuid4().hex}")
    actor = _actor(session_factory, tenant.id)
    catalog = grc_service.create_catalog(tenant.id, "Security baseline", CatalogOriginType.CUSTOM)
    revision = grc_service.create_draft_catalog_revision(
        tenant.id,
        catalog.id,
        json.loads(FIXTURE_PATH.read_text()),
    )

    with session_factory.begin() as session:
        control_id = session.scalars(
            select(CatalogControlIndexRecord.oscal_control_id)
            .where(
                CatalogControlIndexRecord.tenant_id == tenant.id,
                CatalogControlIndexRecord.catalog_revision_id == revision.id,
            )
            .order_by(CatalogControlIndexRecord.oscal_control_id)
        ).first()
    assert control_id is not None

    ssp_service = SystemSecurityPlanService(lambda: session_factory.begin())
    implementation_service = ImplementationService(lambda: session_factory.begin())

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
    implementation = implementation_service.create(
        tenant.id,
        actor,
        catalog.id,
        revision.id,
        control_id,
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

    return {
        "tenant_id": tenant.id,
        "actor": actor,
        "component_id": component["id"],
        "plan": plan,
        "implementation_id": implementation.id,
        "service": ssp_service,
    }


def _responsibility_row_ids(
    session_factory, tenant_id: UUID, implementation_id: UUID
) -> list[UUID]:
    with session_factory.begin() as session:
        return list(
            session.scalars(
                select(ImplementationResponsibilityRecord.id)
                .where(
                    ImplementationResponsibilityRecord.tenant_id == tenant_id,
                    ImplementationResponsibilityRecord.implementation_id == implementation_id,
                )
                .order_by(
                    ImplementationResponsibilityRecord.kind,
                    ImplementationResponsibilityRecord.id,
                )
            )
        )


def test_ssp_membership_mutations_advance_token_and_reject_stale(
    grc_service, session_factory
) -> None:
    context = _prepare_ssp_context(grc_service, session_factory)
    service: SystemSecurityPlanService = context["service"]
    implementation_service = ImplementationService(lambda: session_factory.begin())
    plan = context["plan"]

    token = int(plan["concurrency_version"])
    included = service.associate_implementation(
        context["tenant_id"],
        context["actor"],
        plan["id"],
        context["implementation_id"],
        context["component_id"],
        expected_version=token,
        expected_implementation_version=1,
    )
    assert included["concurrency_version"] == token + 1
    membership_before_stale = service.get_plan(context["tenant_id"], plan["id"])[
        "included_implementations"
    ]
    implementation_before_stale = implementation_service.get(
        context["tenant_id"],
        context["implementation_id"],
    )

    with pytest.raises(StaleSystemSecurityPlanUpdate) as stale:
        service.remove_implementation(
            context["tenant_id"],
            context["actor"],
            plan["id"],
            context["implementation_id"],
            expected_version=token,
        )
    assert stale.value.expected_version == token
    assert stale.value.current_version == token + 1
    membership_after_stale = service.get_plan(context["tenant_id"], plan["id"])[
        "included_implementations"
    ]
    implementation_after_stale = implementation_service.get(
        context["tenant_id"],
        context["implementation_id"],
    )
    assert membership_after_stale == membership_before_stale
    assert implementation_after_stale == implementation_before_stale

    removed = service.remove_implementation(
        context["tenant_id"],
        context["actor"],
        plan["id"],
        context["implementation_id"],
        expected_version=token + 1,
    )
    assert removed["concurrency_version"] == token + 2
    assert service.get_plan(context["tenant_id"], plan["id"])["included_implementations"] == []


def test_ssp_publish_is_idempotent_and_token_aware(grc_service, session_factory) -> None:
    context = _prepare_ssp_context(grc_service, session_factory)
    service: SystemSecurityPlanService = context["service"]
    plan = context["plan"]

    token = int(plan["concurrency_version"])
    included = service.associate_implementation(
        context["tenant_id"],
        context["actor"],
        plan["id"],
        context["implementation_id"],
        context["component_id"],
        expected_version=token,
        expected_implementation_version=1,
    )
    token = included["concurrency_version"]

    first = service.create_version(
        context["tenant_id"],
        context["actor"],
        plan["id"],
        expected_version=token,
    )
    assert first["created"] is True
    assert first["concurrency_version"] == token + 1

    with pytest.raises(StaleSystemSecurityPlanUpdate) as stale:
        service.create_version(
            context["tenant_id"],
            context["actor"],
            plan["id"],
            expected_version=token,
        )
    assert stale.value.current_version == token + 1

    second = service.create_version(
        context["tenant_id"],
        context["actor"],
        plan["id"],
        expected_version=token + 1,
    )
    assert second["created"] is False
    assert second["id"] == first["id"]
    assert second["concurrency_version"] == token + 1
    assert len(service.list_versions(context["tenant_id"], plan["id"])) == 1


def test_ssp_publish_new_snapshot_advances_token_even_same_second(
    grc_service, session_factory, monkeypatch
) -> None:
    context = _prepare_ssp_context(grc_service, session_factory)
    service: SystemSecurityPlanService = context["service"]
    implementation_service = ImplementationService(lambda: session_factory.begin())
    plan = context["plan"]

    included = service.associate_implementation(
        context["tenant_id"],
        context["actor"],
        plan["id"],
        context["implementation_id"],
        context["component_id"],
        expected_version=int(plan["concurrency_version"]),
        expected_implementation_version=1,
    )
    token = int(included["concurrency_version"])

    fixed_now = datetime(2026, 11, 19, 12, 0, 0, tzinfo=UTC)

    class _FrozenDateTime:
        @staticmethod
        def now(_tz: object = UTC) -> datetime:
            return fixed_now

    monkeypatch.setattr(ssp_module, "datetime", _FrozenDateTime)

    first = service.create_version(
        context["tenant_id"],
        context["actor"],
        plan["id"],
        expected_version=token,
    )
    assert first["created"] is True
    assert first["concurrency_version"] == token + 1

    implementation = implementation_service.get(
        context["tenant_id"],
        context["implementation_id"],
    )
    implementation_service.update(
        context["tenant_id"],
        context["actor"],
        implementation.id,
        expected_version=implementation.concurrency_version,
        information=ImplementationInformation(
            "The identity provider now enforces MFA on privileged paths.",
            implementation.status,
            implementation.evidence_references,
            implementation.responsibilities,
            implementation.oscal_implementation_status,
            implementation.oscal_status_explanation,
        ),
    )

    second = service.create_version(
        context["tenant_id"],
        context["actor"],
        plan["id"],
        expected_version=first["concurrency_version"],
    )
    assert second["created"] is True
    assert second["id"] != first["id"]
    assert second["concurrency_version"] == token + 2
    assert len(service.list_versions(context["tenant_id"], plan["id"])) == 2


def test_ssp_publish_rejects_stale_token_under_concurrent_transactions(
    grc_service, session_factory, monkeypatch
) -> None:
    context = _prepare_ssp_context(grc_service, session_factory)
    service: SystemSecurityPlanService = context["service"]
    plan = context["plan"]

    included = service.associate_implementation(
        context["tenant_id"],
        context["actor"],
        plan["id"],
        context["implementation_id"],
        context["component_id"],
        expected_version=int(plan["concurrency_version"]),
        expected_implementation_version=1,
    )
    token = int(included["concurrency_version"])

    release = threading.Barrier(3)
    winner_holding_lock = threading.Event()
    gate_release = threading.Event()
    state_lock = threading.Lock()
    backend_pids: dict[str, int] = {}
    winner_pid: dict[str, int | None] = {"value": None}
    original_get_plan = SystemSecurityPlanService._get_plan

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

    monkeypatch.setattr(SystemSecurityPlanService, "_get_plan", staticmethod(_gated_get_plan))

    def _attempt_publish(worker: str) -> dict[str, object]:
        with session_factory.begin() as thread_session:
            with state_lock:
                backend_pids[worker] = _backend_pid(thread_session)
            concurrent_service = SystemSecurityPlanService(lambda: _bound_scope(thread_session))
            release.wait(timeout=5)
            return concurrent_service.create_version(
                context["tenant_id"],
                context["actor"],
                plan["id"],
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
        except StaleSystemSecurityPlanUpdate as error:
            stale.append(error)

    assert len(published) == 1
    assert published[0]["created"] is True
    assert len(stale) == 1
    assert stale[0].expected_version == token
    assert stale[0].current_version == token + 1

    versions = service.list_versions(context["tenant_id"], plan["id"])
    assert len(versions) == 1
    assert versions[0]["id"] == published[0]["id"]
    persisted = service.get_plan(context["tenant_id"], plan["id"])
    assert persisted["concurrency_version"] == token + 1
    with session_factory.begin() as session:
        stored_version = session.scalar(
            select(SystemSecurityPlanRecord.concurrency_version).where(
                SystemSecurityPlanRecord.tenant_id == context["tenant_id"],
                SystemSecurityPlanRecord.id == plan["id"],
            )
        )
    assert int(stored_version) == token + 1


def test_ssp_update_translates_mapper_stale_error(
    grc_service, session_factory, monkeypatch
) -> None:
    context = _prepare_ssp_context(grc_service, session_factory)
    service: SystemSecurityPlanService = context["service"]
    plan = context["plan"]
    token = int(plan["concurrency_version"])

    original_get_plan = SystemSecurityPlanService._get_plan
    loaded_version_unchanged = {"value": False}

    def _stale_mapper_version_get_plan(session, tenant_id, plan_id, *, lock=False):
        loaded = original_get_plan(session, tenant_id, plan_id, lock=lock)
        if lock:
            loaded_version = int(loaded.concurrency_version)
            session.execute(
                update(SystemSecurityPlanRecord)
                .where(
                    SystemSecurityPlanRecord.tenant_id == tenant_id,
                    SystemSecurityPlanRecord.id == plan_id,
                )
                .values(
                    concurrency_version=SystemSecurityPlanRecord.concurrency_version + 1,
                )
                .execution_options(synchronize_session=False)
            )
            loaded_version_unchanged["value"] = int(loaded.concurrency_version) == loaded_version
        return loaded

    monkeypatch.setattr(
        SystemSecurityPlanService,
        "_get_plan",
        staticmethod(_stale_mapper_version_get_plan),
    )

    with pytest.raises(StaleSystemSecurityPlanUpdate) as error:
        service.update_plan(
            context["tenant_id"],
            context["actor"],
            plan["id"],
            expected_version=token,
            title="Updated title",
            control_implementation_description=plan["control_implementation_description"],
        )

    assert loaded_version_unchanged["value"] is True
    assert isinstance(error.value.__cause__, StaleDataError)
    assert error.value.expected_version == token
    assert error.value.current_version == token
    assert service.get_plan(context["tenant_id"], plan["id"])["title"] == plan["title"]


def test_ssp_publish_translates_mapper_stale_error_and_rolls_back_snapshot(
    grc_service, session_factory, monkeypatch
) -> None:
    context = _prepare_ssp_context(grc_service, session_factory)
    service: SystemSecurityPlanService = context["service"]
    plan = context["plan"]
    included = service.associate_implementation(
        context["tenant_id"],
        context["actor"],
        plan["id"],
        context["implementation_id"],
        context["component_id"],
        expected_version=int(plan["concurrency_version"]),
        expected_implementation_version=1,
    )
    token = int(included["concurrency_version"])

    original_get_plan = SystemSecurityPlanService._get_plan
    loaded_version_unchanged = {"value": False}

    def _stale_mapper_version_get_plan(session, tenant_id, plan_id, *, lock=False):
        loaded = original_get_plan(session, tenant_id, plan_id, lock=lock)
        if lock:
            loaded_version = int(loaded.concurrency_version)
            session.execute(
                update(SystemSecurityPlanRecord)
                .where(
                    SystemSecurityPlanRecord.tenant_id == tenant_id,
                    SystemSecurityPlanRecord.id == plan_id,
                )
                .values(
                    concurrency_version=SystemSecurityPlanRecord.concurrency_version + 1,
                )
                .execution_options(synchronize_session=False)
            )
            loaded_version_unchanged["value"] = int(loaded.concurrency_version) == loaded_version
        return loaded

    monkeypatch.setattr(
        SystemSecurityPlanService,
        "_get_plan",
        staticmethod(_stale_mapper_version_get_plan),
    )

    with pytest.raises(StaleSystemSecurityPlanUpdate) as error:
        service.create_version(
            context["tenant_id"],
            context["actor"],
            plan["id"],
            expected_version=token,
        )

    assert loaded_version_unchanged["value"] is True
    assert isinstance(error.value.__cause__, StaleDataError)
    assert error.value.expected_version == token
    assert error.value.current_version == token
    assert service.list_versions(context["tenant_id"], plan["id"]) == []


def test_stale_include_leaves_membership_and_unassigned_context_unchanged(
    grc_service, session_factory
) -> None:
    context = _prepare_ssp_context(grc_service, session_factory)
    service: SystemSecurityPlanService = context["service"]
    implementation_service = ImplementationService(lambda: session_factory.begin())
    plan = context["plan"]
    token = int(plan["concurrency_version"])

    service.update_plan(
        context["tenant_id"],
        context["actor"],
        plan["id"],
        expected_version=token,
        title=f"{plan['title']} updated",
        control_implementation_description=plan["control_implementation_description"],
    )

    with pytest.raises(StaleSystemSecurityPlanUpdate) as stale:
        service.associate_implementation(
            context["tenant_id"],
            context["actor"],
            plan["id"],
            context["implementation_id"],
            context["component_id"],
            expected_version=token,
            expected_implementation_version=1,
        )

    assert stale.value.expected_version == token
    assert stale.value.current_version == token + 1
    assert service.get_plan(context["tenant_id"], plan["id"])["included_implementations"] == []
    implementation = implementation_service.get(
        context["tenant_id"],
        context["implementation_id"],
    )
    assert implementation.system_id is None
    assert implementation.system_component_id is None


def test_implementation_update_contention_has_single_winner_and_persisted_state(
    grc_service, session_factory, monkeypatch
) -> None:
    context = _prepare_ssp_context(grc_service, session_factory)
    service = ImplementationService(lambda: session_factory.begin())
    implementation = service.get(context["tenant_id"], context["implementation_id"])
    token = int(implementation.concurrency_version)

    release = threading.Barrier(3)
    winner_holding_lock = threading.Event()
    gate_release = threading.Event()
    state_lock = threading.Lock()
    backend_pids: dict[str, int] = {}
    winner_pid: dict[str, int | None] = {"value": None}
    original_get_record = ImplementationService._get_record

    def _gated_get_record(session, tenant_id, implementation_id, *, lock=False):
        loaded = original_get_record(session, tenant_id, implementation_id, lock=lock)
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

    monkeypatch.setattr(ImplementationService, "_get_record", staticmethod(_gated_get_record))

    def _attempt(worker: str, description: str):
        with session_factory.begin() as thread_session:
            with state_lock:
                backend_pids[worker] = _backend_pid(thread_session)
            concurrent_service = ImplementationService(lambda: _bound_scope(thread_session))
            release.wait(timeout=5)
            return concurrent_service.update(
                context["tenant_id"],
                context["actor"],
                implementation.id,
                expected_version=token,
                information=ImplementationInformation(
                    description,
                    implementation.status,
                    implementation.evidence_references,
                    implementation.responsibilities,
                    implementation.oscal_implementation_status,
                    implementation.oscal_status_explanation,
                ),
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(_attempt, "a", "Worker A update"),
            executor.submit(_attempt, "b", "Worker B update"),
        ]
        release.wait(timeout=5)
        try:
            assert winner_holding_lock.wait(timeout=5)
            winner = winner_pid["value"]
            assert winner is not None
            blocked = next(pid for pid in backend_pids.values() if pid != winner)
            _assert_blocked_by(session_factory, blocked_pid=blocked, blocker_pid=winner)
        finally:
            gate_release.set()

    updated = []
    stale = []
    for future in futures:
        try:
            updated.append(future.result())
        except StaleImplementationUpdate as error:
            stale.append(error)

    assert len(updated) == 1
    assert len(stale) == 1
    assert stale[0].expected_version == token
    assert stale[0].current_version == token + 1

    persisted = service.get(context["tenant_id"], implementation.id)
    assert persisted.description == updated[0].description
    assert persisted.concurrency_version == token + 1


def test_implementation_update_and_association_contention_preserves_winner_state(
    grc_service, session_factory, monkeypatch
) -> None:
    context = _prepare_ssp_context(grc_service, session_factory)
    implementation_service = ImplementationService(lambda: session_factory.begin())
    ssp_service: SystemSecurityPlanService = context["service"]
    implementation = implementation_service.get(context["tenant_id"], context["implementation_id"])
    token = int(implementation.concurrency_version)
    plan_token = int(context["plan"]["concurrency_version"])

    winner_holding_lock = threading.Event()
    gate_release = threading.Event()
    backend_pids: dict[str, int] = {}
    state_lock = threading.Lock()
    original_get_record = ImplementationService._get_record

    def _gated_get_record(session, tenant_id, implementation_id, *, lock=False):
        loaded = original_get_record(session, tenant_id, implementation_id, lock=lock)
        if lock:
            winner_holding_lock.set()
            assert gate_release.wait(timeout=5)
        return loaded

    monkeypatch.setattr(ImplementationService, "_get_record", staticmethod(_gated_get_record))

    def _update_worker() -> str:
        with session_factory.begin() as thread_session:
            with state_lock:
                backend_pids["update"] = _backend_pid(thread_session)
            service = ImplementationService(lambda: _bound_scope(thread_session))
            result = service.update(
                context["tenant_id"],
                context["actor"],
                implementation.id,
                expected_version=token,
                information=ImplementationInformation(
                    "Winning implementation update",
                    implementation.status,
                    implementation.evidence_references,
                    implementation.responsibilities,
                    implementation.oscal_implementation_status,
                    implementation.oscal_status_explanation,
                ),
            )
            return result.description

    def _associate_worker() -> dict[str, object]:
        with session_factory.begin() as thread_session:
            with state_lock:
                backend_pids["associate"] = _backend_pid(thread_session)
            service = SystemSecurityPlanService(lambda: _bound_scope(thread_session))
            return service.associate_implementation(
                context["tenant_id"],
                context["actor"],
                context["plan"]["id"],
                implementation.id,
                context["component_id"],
                expected_version=plan_token,
                expected_implementation_version=token,
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_update = executor.submit(_update_worker)
        try:
            assert winner_holding_lock.wait(timeout=5)
            future_associate = executor.submit(_associate_worker)
            for _ in range(200):
                with state_lock:
                    if "associate" in backend_pids:
                        break
                threading.Event().wait(0.01)
            with state_lock:
                assert "associate" in backend_pids
            _assert_blocked_by(
                session_factory,
                blocked_pid=backend_pids["associate"],
                blocker_pid=backend_pids["update"],
            )
        finally:
            gate_release.set()

    assert future_update.result() == "Winning implementation update"
    with pytest.raises(StaleImplementationUpdate) as stale:
        future_associate.result()
    assert stale.value.expected_version == token
    assert stale.value.current_version == token + 1

    persisted = implementation_service.get(context["tenant_id"], implementation.id)
    assert persisted.description == "Winning implementation update"
    assert persisted.system_id is None
    assert persisted.system_component_id is None
    assert (
        ssp_service.get_plan(context["tenant_id"], context["plan"]["id"])[
            "included_implementations"
        ]
        == []
    )


def test_implementation_update_translates_mapper_stale_and_preserves_state(
    grc_service, session_factory, monkeypatch
) -> None:
    context = _prepare_ssp_context(grc_service, session_factory)
    service = ImplementationService(lambda: session_factory.begin())
    implementation = service.get(context["tenant_id"], context["implementation_id"])
    token = int(implementation.concurrency_version)
    old_description = implementation.description

    original_get_record = ImplementationService._get_record
    loaded_version_unchanged = {"value": False}

    def _stale_mapper_version_get_record(session, tenant_id, implementation_id, *, lock=False):
        loaded = original_get_record(session, tenant_id, implementation_id, lock=lock)
        if lock:
            loaded_version = int(loaded.concurrency_version)
            session.execute(
                update(ControlImplementationRecord)
                .where(
                    ControlImplementationRecord.tenant_id == tenant_id,
                    ControlImplementationRecord.id == implementation_id,
                )
                .values(
                    concurrency_version=ControlImplementationRecord.concurrency_version + 1,
                )
                .execution_options(synchronize_session=False)
            )
            loaded_version_unchanged["value"] = int(loaded.concurrency_version) == loaded_version
        return loaded

    monkeypatch.setattr(
        ImplementationService,
        "_get_record",
        staticmethod(_stale_mapper_version_get_record),
    )

    with pytest.raises(StaleImplementationUpdate) as stale:
        service.update(
            context["tenant_id"],
            context["actor"],
            implementation.id,
            expected_version=token,
            information=ImplementationInformation(
                "Mapper stale update",
                implementation.status,
                implementation.evidence_references,
                implementation.responsibilities,
                implementation.oscal_implementation_status,
                implementation.oscal_status_explanation,
            ),
        )

    assert loaded_version_unchanged["value"] is True
    assert isinstance(stale.value.__cause__, StaleDataError)
    assert stale.value.expected_version == token
    assert stale.value.current_version == token
    persisted = service.get(context["tenant_id"], implementation.id)
    assert persisted.description == old_description
    assert persisted.responsibilities == implementation.responsibilities


def test_associate_translates_implementation_flush_stale_and_rolls_back(
    grc_service, session_factory, monkeypatch
) -> None:
    context = _prepare_ssp_context(grc_service, session_factory)
    service: SystemSecurityPlanService = context["service"]
    implementation_service = ImplementationService(lambda: session_factory.begin())
    plan = context["plan"]
    implementation = implementation_service.get(context["tenant_id"], context["implementation_id"])
    token = int(plan["concurrency_version"])
    impl_token = int(implementation.concurrency_version)

    injected = {"value": False}
    original_flush = ssp_module.Session.flush

    def _flush_with_impl_stale(self, *args, **kwargs):
        dirty_implementation = any(
            isinstance(item, ControlImplementationRecord) and item.id == implementation.id
            for item in self.dirty
        )
        if dirty_implementation and not injected["value"]:
            injected["value"] = True
            with self.no_autoflush:
                self.execute(
                    update(ControlImplementationRecord)
                    .where(
                        ControlImplementationRecord.tenant_id == context["tenant_id"],
                        ControlImplementationRecord.id == implementation.id,
                    )
                    .values(
                        concurrency_version=ControlImplementationRecord.concurrency_version + 1,
                    )
                    .execution_options(synchronize_session=False)
                )
        return original_flush(self, *args, **kwargs)

    monkeypatch.setattr(ssp_module.Session, "flush", _flush_with_impl_stale)

    with pytest.raises(StaleImplementationUpdate) as stale:
        service.associate_implementation(
            context["tenant_id"],
            context["actor"],
            plan["id"],
            implementation.id,
            context["component_id"],
            expected_version=token,
            expected_implementation_version=impl_token,
        )

    assert isinstance(stale.value.__cause__, StaleDataError)
    assert stale.value.expected_version == impl_token
    assert stale.value.current_version == impl_token
    assert service.get_plan(context["tenant_id"], plan["id"])["included_implementations"] == []
    persisted = implementation_service.get(context["tenant_id"], implementation.id)
    assert persisted.concurrency_version == impl_token
    assert persisted.system_id is None
    assert persisted.system_component_id is None


def test_associate_translates_ssp_flush_after_implementation_flush_and_rolls_back(
    grc_service, session_factory, monkeypatch
) -> None:
    context = _prepare_ssp_context(grc_service, session_factory)
    service: SystemSecurityPlanService = context["service"]
    implementation_service = ImplementationService(lambda: session_factory.begin())
    plan = context["plan"]
    implementation = implementation_service.get(context["tenant_id"], context["implementation_id"])
    token = int(plan["concurrency_version"])
    impl_token = int(implementation.concurrency_version)

    state = {"impl_seen": False, "plan_injected": False}
    original_flush = ssp_module.Session.flush

    def _flush_with_plan_stale(self, *args, **kwargs):
        dirty_implementation = any(
            isinstance(item, ControlImplementationRecord) and item.id == implementation.id
            for item in self.dirty
        )
        dirty_plan = any(
            isinstance(item, SystemSecurityPlanRecord) and item.id == plan["id"]
            for item in self.dirty
        )
        if dirty_implementation:
            state["impl_seen"] = True
        if (
            state["impl_seen"]
            and dirty_plan
            and not dirty_implementation
            and not state["plan_injected"]
        ):
            state["plan_injected"] = True
            with self.no_autoflush:
                self.execute(
                    update(SystemSecurityPlanRecord)
                    .where(
                        SystemSecurityPlanRecord.tenant_id == context["tenant_id"],
                        SystemSecurityPlanRecord.id == plan["id"],
                    )
                    .values(
                        concurrency_version=SystemSecurityPlanRecord.concurrency_version + 1,
                    )
                    .execution_options(synchronize_session=False)
                )
        return original_flush(self, *args, **kwargs)

    monkeypatch.setattr(ssp_module.Session, "flush", _flush_with_plan_stale)

    with pytest.raises(StaleSystemSecurityPlanUpdate) as stale:
        service.associate_implementation(
            context["tenant_id"],
            context["actor"],
            plan["id"],
            implementation.id,
            context["component_id"],
            expected_version=token,
            expected_implementation_version=impl_token,
        )

    assert isinstance(stale.value.__cause__, StaleDataError)
    assert stale.value.expected_version == token
    assert stale.value.current_version == token
    assert service.get_plan(context["tenant_id"], plan["id"])["included_implementations"] == []
    persisted = implementation_service.get(context["tenant_id"], implementation.id)
    assert persisted.concurrency_version == impl_token
    assert persisted.system_id is None
    assert persisted.system_component_id is None


def test_responsibility_only_update_advances_token_without_timestamp_dependency(
    grc_service, session_factory, monkeypatch
) -> None:
    context = _prepare_ssp_context(grc_service, session_factory)
    service = ImplementationService(lambda: session_factory.begin())
    implementation = service.get(context["tenant_id"], context["implementation_id"])

    class _FrozenDateTime:
        @staticmethod
        def now(_tz: object = UTC) -> datetime:
            return implementation.updated_at

    monkeypatch.setattr(implementation_module, "datetime", _FrozenDateTime)

    before_version = implementation.concurrency_version
    before_updated_at = implementation.updated_at
    changed = service.update(
        context["tenant_id"],
        context["actor"],
        implementation.id,
        expected_version=before_version,
        information=ImplementationInformation(
            implementation.description,
            implementation.status,
            implementation.evidence_references,
            [
                Responsibility(ResponsibilityKind.ACCOUNTABLE, context["actor"], "Owner"),
                Responsibility(ResponsibilityKind.PARTICIPANT, None, "Security team"),
            ],
            implementation.oscal_implementation_status,
            implementation.oscal_status_explanation,
        ),
    )
    assert changed.concurrency_version == before_version + 1
    assert changed.updated_at == before_updated_at

    row_ids_before_noop = _responsibility_row_ids(
        session_factory,
        context["tenant_id"],
        implementation.id,
    )
    noop = service.update(
        context["tenant_id"],
        context["actor"],
        implementation.id,
        expected_version=changed.concurrency_version,
        information=ImplementationInformation(
            changed.description,
            changed.status,
            changed.evidence_references,
            list(reversed(changed.responsibilities)),
            changed.oscal_implementation_status,
            changed.oscal_status_explanation,
        ),
    )
    row_ids_after_noop = _responsibility_row_ids(
        session_factory,
        context["tenant_id"],
        implementation.id,
    )
    assert noop.concurrency_version == changed.concurrency_version
    assert noop.updated_at == changed.updated_at
    assert row_ids_after_noop == row_ids_before_noop


def test_association_unchanged_context_and_removal_preserve_implementation_token(
    grc_service, session_factory
) -> None:
    context = _prepare_ssp_context(grc_service, session_factory)
    service: SystemSecurityPlanService = context["service"]
    implementation_service = ImplementationService(lambda: session_factory.begin())
    plan_one = context["plan"]
    implementation_id = context["implementation_id"]

    include_one = service.associate_implementation(
        context["tenant_id"],
        context["actor"],
        plan_one["id"],
        implementation_id,
        context["component_id"],
        expected_version=int(plan_one["concurrency_version"]),
        expected_implementation_version=1,
    )
    implementation_after_first = implementation_service.get(context["tenant_id"], implementation_id)

    plan_two = service.create_plan(
        context["tenant_id"],
        context["actor"],
        plan_one["system_id"],
        catalog_id=plan_one["catalog_id"],
        revision_id=plan_one["revision_id"],
        title="Second SSP",
        control_implementation_description="Second SSP working state.",
    )
    include_two = service.associate_implementation(
        context["tenant_id"],
        context["actor"],
        plan_two["id"],
        implementation_id,
        context["component_id"],
        expected_version=int(plan_two["concurrency_version"]),
        expected_implementation_version=implementation_after_first.concurrency_version,
    )
    assert (
        include_two["implementation_concurrency_version"]
        == implementation_after_first.concurrency_version
    )

    removed_two = service.remove_implementation(
        context["tenant_id"],
        context["actor"],
        plan_two["id"],
        implementation_id,
        expected_version=include_two["concurrency_version"],
    )
    assert removed_two["concurrency_version"] == include_two["concurrency_version"] + 1
    after_remove_two = implementation_service.get(context["tenant_id"], implementation_id)
    assert after_remove_two.system_id == implementation_after_first.system_id
    assert after_remove_two.system_component_id == implementation_after_first.system_component_id
    assert after_remove_two.concurrency_version == implementation_after_first.concurrency_version

    removed_one = service.remove_implementation(
        context["tenant_id"],
        context["actor"],
        plan_one["id"],
        implementation_id,
        expected_version=include_one["concurrency_version"],
    )
    assert removed_one["concurrency_version"] == include_one["concurrency_version"] + 1
    after_remove_one = implementation_service.get(context["tenant_id"], implementation_id)
    assert after_remove_one.system_id == implementation_after_first.system_id
    assert after_remove_one.system_component_id == implementation_after_first.system_component_id
    assert after_remove_one.concurrency_version == implementation_after_first.concurrency_version


def test_association_lock_order_is_compatible_with_validation_component_lock(
    grc_service, session_factory, monkeypatch
) -> None:
    context = _prepare_ssp_context(grc_service, session_factory)
    plan = context["plan"]

    holding_component_lock = threading.Event()
    release_component_lock = threading.Event()
    backend_pids: dict[str, int] = {}
    original_get_component = SystemSecurityPlanService._get_component

    def _gated_get_component(
        session,
        tenant_id,
        system_id,
        component_id,
        *,
        lock=False,
    ):
        component = original_get_component(
            session,
            tenant_id,
            system_id,
            component_id,
            lock=lock,
        )
        if lock:
            holding_component_lock.set()
            assert release_component_lock.wait(timeout=5)
        return component

    monkeypatch.setattr(
        SystemSecurityPlanService,
        "_get_component",
        staticmethod(_gated_get_component),
    )

    def _associate() -> dict[str, object]:
        with session_factory.begin() as thread_session:
            backend_pids["associate"] = _backend_pid(thread_session)
            threaded_service = SystemSecurityPlanService(lambda: _bound_scope(thread_session))
            return threaded_service.associate_implementation(
                context["tenant_id"],
                context["actor"],
                plan["id"],
                context["implementation_id"],
                context["component_id"],
                expected_version=int(plan["concurrency_version"]),
                expected_implementation_version=1,
            )

    def _validate() -> dict[str, object]:
        with session_factory.begin() as thread_session:
            backend_pids["validate"] = _backend_pid(thread_session)
            threaded_service = SystemSecurityPlanService(lambda: _bound_scope(thread_session))
            return threaded_service.validate_plan(context["tenant_id"], plan["id"])

    with ThreadPoolExecutor(max_workers=2) as executor:
        include_future = executor.submit(_associate)
        assert holding_component_lock.wait(timeout=5)
        validate_future = executor.submit(_validate)
        try:
            for _ in range(200):
                if "validate" in backend_pids:
                    break
                threading.Event().wait(0.01)
            assert "validate" in backend_pids
            _assert_blocked_by(
                session_factory,
                blocked_pid=backend_pids["validate"],
                blocker_pid=backend_pids["associate"],
            )
        finally:
            release_component_lock.set()

    include_result = include_future.result()
    validate_result = validate_future.result()
    assert include_result["concurrency_version"] == int(plan["concurrency_version"]) + 1
    assert isinstance(validate_result["valid"], bool)
    with session_factory.begin() as session:
        persisted_count = session.scalar(
            select(func.count())
            .select_from(SystemSecurityPlanImplementationRecord)
            .where(
                SystemSecurityPlanImplementationRecord.tenant_id == context["tenant_id"],
                SystemSecurityPlanImplementationRecord.system_security_plan_id == plan["id"],
            )
        )
    assert int(persisted_count or 0) == 1




