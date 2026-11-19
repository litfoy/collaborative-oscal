from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.orm.exc import StaleDataError

import app.application.system_security_plans as ssp_module
from app.application.implementations import ImplementationService
from app.application.system_security_plans import (
    StaleSystemSecurityPlanUpdate,
    SystemSecurityPlanService,
)
from app.domain.catalogs.models import CatalogOriginType
from app.domain.implementations import (
    ImplementationInformation,
    ImplementationStatus,
    OscalImplementationStatus,
)
from app.persistence.identity import SQLIdentityRepository, SQLMembershipRepository
from app.persistence.models import CatalogControlIndexRecord, SystemSecurityPlanRecord

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
        ImplementationInformation(
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




