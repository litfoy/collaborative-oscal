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
from sqlalchemy import select, text
from sqlalchemy.orm.exc import StaleDataError

from app.application.component_definitions import (
    ComponentDefinitionService,
    ComponentInput,
    ComponentRequirementInput,
    StaleComponentDefinitionUpdate,
)
from app.persistence.identity import SQLIdentityRepository, SQLMembershipRepository
from app.persistence.models import ComponentDefinitionSourceRecord

pytestmark = pytest.mark.integration
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "oscal_catalog.json"


@contextmanager
def _bound_scope(session):
    yield session


def _catalog_document() -> dict:
    return json.loads(FIXTURE_PATH.read_text())


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


def _actor(session_factory, tenant_id: UUID):
    with session_factory.begin() as session:
        identity = SQLIdentityRepository(session).get_or_create(
            issuer="https://issuer.example.test",
            subject=f"component-concurrency-{uuid4()}",
            display_name="Component Concurrency Tester",
            email=None,
        )
        SQLMembershipRepository(session).assign(
            tenant_id=tenant_id,
            user_id=identity.id,
            role="catalog_editor",
            status="active",
        )
    return identity


def _source_projection(
    session_factory,
    *,
    tenant_id: UUID,
    document_id: UUID,
) -> list[tuple[UUID, UUID, str]]:
    with session_factory.begin() as session:
        rows = session.execute(
            select(
                ComponentDefinitionSourceRecord.catalog_id,
                ComponentDefinitionSourceRecord.revision_id,
                ComponentDefinitionSourceRecord.oscal_control_id,
            )
            .where(
                ComponentDefinitionSourceRecord.tenant_id == tenant_id,
                ComponentDefinitionSourceRecord.document_id == document_id,
            )
            .order_by(
                ComponentDefinitionSourceRecord.catalog_id,
                ComponentDefinitionSourceRecord.revision_id,
                ComponentDefinitionSourceRecord.oscal_control_id,
            )
        ).all()
    return [(catalog_id, revision_id, control_id) for catalog_id, revision_id, control_id in rows]


def _prepare_context(grc_service, session_factory):
    from app.domain.catalogs.models import CatalogOriginType

    tenant = grc_service.create_tenant(
        "Component concurrency",
        f"component-concurrency-{uuid4().hex}",
    )
    actor = _actor(session_factory, tenant.id)
    catalog = grc_service.create_catalog(tenant.id, "Security", CatalogOriginType.CUSTOM)
    revision = grc_service.create_draft_catalog_revision(
        tenant.id,
        catalog.id,
        _catalog_document(),
    )
    service = ComponentDefinitionService(lambda: session_factory.begin())
    created = service.create(
        tenant.id,
        actor.id,
        "Multifactor authentication",
        "policy",
        "Reusable guidance",
        [
            ComponentRequirementInput(
                catalog.id,
                revision.id,
                "ac-1",
                "Require MFA for privileged access.",
            )
        ],
    )
    return {
        "tenant_id": tenant.id,
        "actor_id": actor.id,
        "catalog_id": catalog.id,
        "revision_id": revision.id,
        "service": service,
        "created": created,
    }


def test_component_definition_update_uses_pg_blocking_pids_and_rejects_stale_tokens(
    grc_service, session_factory, monkeypatch
) -> None:
    context = _prepare_context(grc_service, session_factory)
    created = context["created"]
    token = created.concurrency_version

    release = threading.Barrier(3)
    winner_holding_lock = threading.Event()
    gate_release = threading.Event()
    state_lock = threading.Lock()
    backend_pids: dict[str, int] = {}
    winner_pid: dict[str, int | None] = {"value": None}
    original_get_record = ComponentDefinitionService._get_record

    def _gated_get_record(session, tenant_id, document_id, *, lock=False):
        record = original_get_record(session, tenant_id, document_id, lock=lock)
        if lock and document_id == created.id:
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
        return record

    monkeypatch.setattr(
        ComponentDefinitionService,
        "_get_record",
        staticmethod(_gated_get_record),
    )

    def _attempt(worker: str):
        with session_factory.begin() as thread_session:
            with state_lock:
                backend_pids[worker] = _backend_pid(thread_session)
            concurrent_service = ComponentDefinitionService(lambda: _bound_scope(thread_session))
            release.wait(timeout=5)
            return concurrent_service.update(
                context["tenant_id"],
                context["actor_id"],
                created.id,
                token,
                f"Winner {worker}",
                [
                    ComponentInput(
                        created.components[0].id,
                        created.components[0].type,
                        created.components[0].title,
                        created.components[0].description,
                        [
                            ComponentRequirementInput(
                                context["catalog_id"],
                                context["revision_id"],
                                "ac-1",
                                "Require MFA for privileged access.",
                            )
                        ],
                    )
                ],
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(_attempt, "a"), executor.submit(_attempt, "b")]
        release.wait(timeout=5)
        try:
            assert winner_holding_lock.wait(timeout=5)
            winner = winner_pid["value"]
            assert winner is not None
            blocked = next(pid for pid in backend_pids.values() if pid != winner)
            _assert_blocked_by(session_factory, blocked_pid=blocked, blocker_pid=winner)
        finally:
            gate_release.set()

    updated: list[object] = []
    stale: list[StaleComponentDefinitionUpdate] = []
    for future in futures:
        try:
            updated.append(future.result())
        except StaleComponentDefinitionUpdate as error:
            stale.append(error)

    assert len(updated) == 1
    assert len(stale) == 1
    assert stale[0].expected_version == token
    assert stale[0].current_version == token + 1

    persisted = context["service"].get(context["tenant_id"], created.id)
    assert persisted.concurrency_version == token + 1


def test_component_definition_mapper_stale_translation_rolls_back_document_and_sources(
    grc_service, session_factory, monkeypatch
) -> None:
    context = _prepare_context(grc_service, session_factory)
    service = context["service"]
    created = context["created"]
    before = service.get(context["tenant_id"], created.id)
    before_export = service.export(context["tenant_id"], created.id)
    before_sources = _source_projection(
        session_factory,
        tenant_id=context["tenant_id"],
        document_id=created.id,
    )

    original_validate = ComponentDefinitionService._lock_and_validate_sources
    bumped = {"done": False}

    def _stale_validate(session, tenant_id, requirements):
        original_validate(session, tenant_id, requirements)
        if bumped["done"]:
            return
        session.execute(
            text(
                "UPDATE component_definitions "
                "SET concurrency_version = concurrency_version + 1 "
                "WHERE tenant_id = :tenant_id AND id = :document_id"
            ),
            {
                "tenant_id": context["tenant_id"],
                "document_id": created.id,
            },
        )
        bumped["done"] = True

    monkeypatch.setattr(
        ComponentDefinitionService,
        "_lock_and_validate_sources",
        staticmethod(_stale_validate),
    )

    with pytest.raises(StaleComponentDefinitionUpdate) as stale:
        service.update(
            context["tenant_id"],
            context["actor_id"],
            created.id,
            before.concurrency_version,
            "Changed title",
            [
                ComponentInput(
                    before.components[0].id,
                    before.components[0].type,
                    before.components[0].title,
                    "Changed reusable guidance.",
                    [
                        ComponentRequirementInput(
                            context["catalog_id"],
                            context["revision_id"],
                            "ac-1",
                            "Require MFA for privileged access.",
                        )
                    ],
                )
            ],
        )

    assert isinstance(stale.value.__cause__, StaleDataError)
    assert stale.value.expected_version == before.concurrency_version
    assert stale.value.current_version == before.concurrency_version

    after = service.get(context["tenant_id"], created.id)
    after_export = service.export(context["tenant_id"], created.id)
    after_sources = _source_projection(
        session_factory,
        tenant_id=context["tenant_id"],
        document_id=created.id,
    )
    assert after.title == before.title
    assert after_export == before_export
    assert after_sources == before_sources


def test_component_definition_stale_delete_preserves_document_and_source_projection(
    grc_service, session_factory
) -> None:
    context = _prepare_context(grc_service, session_factory)
    service = context["service"]
    created = context["created"]
    source_before = _source_projection(
        session_factory,
        tenant_id=context["tenant_id"],
        document_id=created.id,
    )

    updated = service.update(
        context["tenant_id"],
        context["actor_id"],
        created.id,
        created.concurrency_version,
        "Changed title",
        [
            ComponentInput(
                created.components[0].id,
                created.components[0].type,
                created.components[0].title,
                created.components[0].description,
                [
                    ComponentRequirementInput(
                        context["catalog_id"],
                        context["revision_id"],
                        "ac-1",
                        "Require MFA for privileged access.",
                    )
                ],
            )
        ],
    )

    with pytest.raises(StaleComponentDefinitionUpdate) as stale_document:
        service.delete(
            context["tenant_id"],
            created.id,
            expected_version=created.concurrency_version,
        )
    assert stale_document.value.expected_version == created.concurrency_version
    assert stale_document.value.current_version == updated.concurrency_version

    with pytest.raises(StaleComponentDefinitionUpdate) as stale_component:
        service.delete_component(
            context["tenant_id"],
            context["actor_id"],
            created.id,
            created.components[0].id,
            expected_version=created.concurrency_version,
        )
    assert stale_component.value.expected_version == created.concurrency_version
    assert stale_component.value.current_version == updated.concurrency_version

    persisted = service.get(context["tenant_id"], created.id)
    source_after = _source_projection(
        session_factory,
        tenant_id=context["tenant_id"],
        document_id=created.id,
    )
    assert persisted.id == created.id
    assert source_after == source_before



