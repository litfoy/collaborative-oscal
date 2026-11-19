# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text, update
from sqlalchemy.orm.exc import StaleDataError

from app.application.component_definitions import (
    ComponentDefinitionService,
)
from app.application.system_security_plans import (
    StaleInformationSystemUpdate,
    StaleSystemComponentUpdate,
    SystemSecurityPlanService,
)
from app.persistence.identity import SQLIdentityRepository, SQLMembershipRepository
from app.persistence.models import InformationSystemRecord, SystemComponentRecord

pytestmark = pytest.mark.integration


@contextmanager
def _bound_scope(session):
    yield session


def _actor(session_factory, tenant_id: UUID) -> UUID:
    with session_factory.begin() as session:
        identity = SQLIdentityRepository(session).get_or_create(
            issuer="https://issuer.example.test",
            subject=f"system-component-concurrency-{uuid4()}",
            display_name="System Component Concurrency",
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


def _prepare_context(grc_service, session_factory) -> dict[str, object]:
    tenant = grc_service.create_tenant(
        "System component concurrency tenant", f"system-component-{uuid4().hex}"
    )
    actor = _actor(session_factory, tenant.id)
    service = SystemSecurityPlanService(lambda: session_factory.begin())
    definitions = ComponentDefinitionService(lambda: session_factory.begin())

    system = service.create_system(
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
    native_component = service.create_component(
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
    another_component = service.create_component(
        tenant.id,
        actor,
        system["id"],
        component_type="software",
        title="Admin portal",
        description="Administrative portal deployment.",
        purpose=None,
        status="operational",
        status_remarks=None,
    )

    definition = definitions.create(
        tenant.id,
        actor,
        "Reusable identity measure",
        "service",
        "Reusable guidance.",
        [],
    )
    adopted = service.adopt_component_definition(
        tenant.id,
        actor,
        system["id"],
        definition.id,
        definition.components[0].id,
        title="Policy enforcement component",
        description="Deployed policy enforcement component.",
        purpose=None,
        status="operational",
        status_remarks=None,
    )

    return {
        "tenant_id": tenant.id,
        "actor": actor,
        "service": service,
        "system": system,
        "native": native_component,
        "another": another_component,
        "adopted": adopted,
    }


def test_system_and_component_tokens_initialize_and_remain_independent(
    grc_service, session_factory
) -> None:
    context = _prepare_context(grc_service, session_factory)
    service: SystemSecurityPlanService = context["service"]

    system = context["system"]
    native = context["native"]
    adopted = context["adopted"]

    assert system["concurrency_version"] == 1
    assert native["concurrency_version"] == 1
    assert adopted["concurrency_version"] == 1
    assert adopted["source_snapshot_id"] is not None

    updated_component = service.update_component(
        context["tenant_id"],
        context["actor"],
        system["id"],
        native["id"],
        expected_version=native["concurrency_version"],
        title="Identity provider v2",
        description=native["component"]["description"],
        purpose=native["component"].get("purpose"),
        status=native["component"]["status"]["state"],
        status_remarks=native["component"]["status"].get("remarks"),
    )
    assert updated_component["concurrency_version"] == 2
    assert service.get_system(context["tenant_id"], system["id"])["concurrency_version"] == 1


def test_noop_and_nested_only_updates_for_system_and_component(
    grc_service, session_factory
) -> None:
    context = _prepare_context(grc_service, session_factory)
    service: SystemSecurityPlanService = context["service"]
    system = context["system"]
    native = context["native"]

    no_op_system = service.update_system(
        context["tenant_id"],
        context["actor"],
        system["id"],
        expected_version=system["concurrency_version"],
        name=system["name"],
        description=system["description"],
        system_boundary=system["system_boundary"],
        system_ids=system["system_ids"],
        information_types=system["information_types"],
        operational_status=system["operational_status"],
        status_remarks=system["status_remarks"],
        security_sensitivity_level=system["security_sensitivity_level"],
    )
    assert no_op_system["concurrency_version"] == 1

    nested_system = service.update_system(
        context["tenant_id"],
        context["actor"],
        system["id"],
        expected_version=no_op_system["concurrency_version"],
        name=system["name"],
        description=system["description"],
        system_boundary=system["system_boundary"],
        system_ids=system["system_ids"],
        information_types=[
            {
                **system["information_types"][0],
                "description": "Updated nested description.",
            }
        ],
        operational_status=system["operational_status"],
        status_remarks=system["status_remarks"],
        security_sensitivity_level=system["security_sensitivity_level"],
    )
    assert nested_system["concurrency_version"] == 2

    no_op_component = service.update_component(
        context["tenant_id"],
        context["actor"],
        system["id"],
        native["id"],
        expected_version=native["concurrency_version"],
        title=native["component"]["title"],
        description=native["component"]["description"],
        purpose=native["component"].get("purpose"),
        status=native["component"]["status"]["state"],
        status_remarks=native["component"]["status"].get("remarks"),
    )
    assert no_op_component["concurrency_version"] == 1

    nested_component = service.update_component(
        context["tenant_id"],
        context["actor"],
        system["id"],
        native["id"],
        expected_version=no_op_component["concurrency_version"],
        title=native["component"]["title"],
        description="Updated nested component description.",
        purpose=native["component"].get("purpose"),
        status=native["component"]["status"]["state"],
        status_remarks=native["component"]["status"].get("remarks"),
    )
    assert nested_component["concurrency_version"] == 2


def test_component_tokens_are_independent_between_components(grc_service, session_factory) -> None:
    context = _prepare_context(grc_service, session_factory)
    service: SystemSecurityPlanService = context["service"]
    system = context["system"]
    native = context["native"]
    another = context["another"]

    updated_native = service.update_component(
        context["tenant_id"],
        context["actor"],
        system["id"],
        native["id"],
        expected_version=native["concurrency_version"],
        title="Identity provider v2",
        description=native["component"]["description"],
        purpose=native["component"].get("purpose"),
        status=native["component"]["status"]["state"],
        status_remarks=native["component"]["status"].get("remarks"),
    )
    unchanged_other = next(
        item
        for item in service.list_components(context["tenant_id"], system["id"])
        if item["id"] == another["id"]
    )

    assert updated_native["concurrency_version"] == 2
    assert unchanged_other["concurrency_version"] == 1


def test_system_update_translates_mapper_stale_error(
    grc_service, session_factory, monkeypatch
) -> None:
    context = _prepare_context(grc_service, session_factory)
    service: SystemSecurityPlanService = context["service"]
    system = context["system"]
    token = int(system["concurrency_version"])

    original_get_system = SystemSecurityPlanService._get_system

    def _stale_mapper_version_get_system(session, tenant_id, system_id, *, lock=False):
        loaded = original_get_system(session, tenant_id, system_id, lock=lock)
        if lock:
            session.execute(
                update(InformationSystemRecord)
                .where(
                    InformationSystemRecord.tenant_id == tenant_id,
                    InformationSystemRecord.id == system_id,
                )
                .values(
                    concurrency_version=InformationSystemRecord.concurrency_version + 1,
                )
                .execution_options(synchronize_session=False)
            )
        return loaded

    monkeypatch.setattr(
        SystemSecurityPlanService,
        "_get_system",
        staticmethod(_stale_mapper_version_get_system),
    )

    with pytest.raises(StaleInformationSystemUpdate) as error:
        service.update_system(
            context["tenant_id"],
            context["actor"],
            system["id"],
            expected_version=token,
            name="Updated name",
            description=system["description"],
            system_boundary=system["system_boundary"],
            system_ids=system["system_ids"],
            information_types=system["information_types"],
            operational_status=system["operational_status"],
            status_remarks=system["status_remarks"],
            security_sensitivity_level=system["security_sensitivity_level"],
        )

    assert isinstance(error.value.__cause__, StaleDataError)
    assert error.value.expected_version == token
    assert error.value.current_version == token
    assert (
        service.get_system(context["tenant_id"], system["id"])["name"]
        == system["name"]
    )


def test_component_update_translates_mapper_stale_error(
    grc_service, session_factory, monkeypatch
) -> None:
    context = _prepare_context(grc_service, session_factory)
    service: SystemSecurityPlanService = context["service"]
    system = context["system"]
    native = context["native"]
    token = int(native["concurrency_version"])

    original_get_component = SystemSecurityPlanService._get_component

    def _stale_mapper_version_get_component(
        session, tenant_id, system_id, component_id, *, lock=False
    ):
        loaded = original_get_component(
            session,
            tenant_id,
            system_id,
            component_id,
            lock=lock,
        )
        if lock:
            session.execute(
                update(SystemComponentRecord)
                .where(
                    SystemComponentRecord.tenant_id == tenant_id,
                    SystemComponentRecord.system_id == system_id,
                    SystemComponentRecord.id == component_id,
                )
                .values(
                    concurrency_version=SystemComponentRecord.concurrency_version + 1,
                )
                .execution_options(synchronize_session=False)
            )
        return loaded

    monkeypatch.setattr(
        SystemSecurityPlanService,
        "_get_component",
        staticmethod(_stale_mapper_version_get_component),
    )

    with pytest.raises(StaleSystemComponentUpdate) as error:
        service.update_component(
            context["tenant_id"],
            context["actor"],
            system["id"],
            native["id"],
            expected_version=token,
            title="Updated title",
            description=native["component"]["description"],
            purpose=native["component"].get("purpose"),
            status=native["component"]["status"]["state"],
            status_remarks=native["component"]["status"].get("remarks"),
        )

    assert isinstance(error.value.__cause__, StaleDataError)
    assert error.value.expected_version == token
    assert error.value.current_version == token
    unchanged = next(
        item
        for item in service.list_components(context["tenant_id"], system["id"])
        if item["id"] == native["id"]
    )
    assert unchanged["component"]["title"] == native["component"]["title"]


def test_system_and_component_updates_block_concurrent_transactions(
    grc_service, session_factory, monkeypatch
) -> None:
    context = _prepare_context(grc_service, session_factory)
    service: SystemSecurityPlanService = context["service"]
    system = context["system"]
    native = context["native"]

    release = threading.Barrier(3)
    winner_holding_lock = threading.Event()
    gate_release = threading.Event()
    state_lock = threading.Lock()
    backend_pids: dict[str, int] = {}
    winner_pid: dict[str, int | None] = {"value": None}

    original_get_system = SystemSecurityPlanService._get_system

    def _gated_get_system(session, tenant_id, system_id, *, lock=False):
        loaded = original_get_system(session, tenant_id, system_id, lock=lock)
        if lock and system_id == system["id"]:
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

    monkeypatch.setattr(SystemSecurityPlanService, "_get_system", staticmethod(_gated_get_system))

    def _attempt_system(worker: str) -> dict[str, object]:
        with session_factory.begin() as thread_session:
            with state_lock:
                backend_pids[worker] = _backend_pid(thread_session)
            concurrent_service = SystemSecurityPlanService(lambda: _bound_scope(thread_session))
            release.wait(timeout=5)
            return concurrent_service.update_system(
                context["tenant_id"],
                context["actor"],
                system["id"],
                expected_version=1,
                name=f"System by {worker}",
                description=system["description"],
                system_boundary=system["system_boundary"],
                system_ids=system["system_ids"],
                information_types=system["information_types"],
                operational_status=system["operational_status"],
                status_remarks=system["status_remarks"],
                security_sensitivity_level=system["security_sensitivity_level"],
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(_attempt_system, "a"), executor.submit(_attempt_system, "b")]
        release.wait(timeout=5)
        try:
            assert winner_holding_lock.wait(timeout=5)
            winner = winner_pid["value"]
            assert winner is not None
            blocked = next(pid for pid in backend_pids.values() if pid != winner)
            _assert_blocked_by(session_factory, blocked_pid=blocked, blocker_pid=winner)
        finally:
            gate_release.set()

    system_results = []
    system_stale = []
    for future in futures:
        try:
            system_results.append(future.result())
        except StaleInformationSystemUpdate as error:
            system_stale.append(error)

    assert len(system_results) == 1
    assert len(system_stale) == 1
    assert system_stale[0].expected_version == 1
    assert system_stale[0].current_version == 2

    persisted = service.get_system(context["tenant_id"], system["id"])
    assert persisted["concurrency_version"] == 2
    assert persisted["name"] == system_results[0]["name"]

    # Reset lock orchestration for component test.
    release = threading.Barrier(3)
    winner_holding_lock = threading.Event()
    gate_release = threading.Event()
    backend_pids = {}
    winner_pid = {"value": None}

    original_get_component = SystemSecurityPlanService._get_component

    def _gated_get_component(session, tenant_id, system_id, component_id, *, lock=False):
        loaded = original_get_component(
            session, tenant_id, system_id, component_id, lock=lock
        )
        if lock and component_id == native["id"]:
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

    monkeypatch.setattr(
        SystemSecurityPlanService,
        "_get_component",
        staticmethod(_gated_get_component),
    )

    def _attempt_component(worker: str) -> dict[str, object]:
        with session_factory.begin() as thread_session:
            with state_lock:
                backend_pids[worker] = _backend_pid(thread_session)
            concurrent_service = SystemSecurityPlanService(lambda: _bound_scope(thread_session))
            release.wait(timeout=5)
            return concurrent_service.update_component(
                context["tenant_id"],
                context["actor"],
                system["id"],
                native["id"],
                expected_version=1,
                title=f"Component by {worker}",
                description=native["component"]["description"],
                purpose=native["component"].get("purpose"),
                status=native["component"]["status"]["state"],
                status_remarks=native["component"]["status"].get("remarks"),
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(_attempt_component, "a"),
            executor.submit(_attempt_component, "b"),
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

    results = []
    stale = []
    for future in futures:
        try:
            results.append(future.result())
        except StaleSystemComponentUpdate as error:
            stale.append(error)

    assert len(results) == 1
    assert len(stale) == 1
    assert stale[0].expected_version == 1
    assert stale[0].current_version == 2
    persisted_component = next(
        item
        for item in service.list_components(context["tenant_id"], system["id"])
        if item["id"] == native["id"]
    )
    assert persisted_component["concurrency_version"] == 2
    assert persisted_component["component"]["title"] == results[0]["component"]["title"]






