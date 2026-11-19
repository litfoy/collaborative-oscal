from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm.exc import StaleDataError

from app.application.catalog_import import CatalogImportService
from app.application.implementations import ImplementationService
from app.application.mappings import MappingService, StaleMappingCollectionUpdate
from app.application.profiles import ProfileService, StaleProfileUpdate
from app.domain.implementations import (
    ImplementationInformation,
    ImplementationStatus,
    OscalImplementationStatus,
)
from app.domain.mappings import MappingEntrySpec, MappingPairSpec
from app.domain.profiles.models import ProfileImport
from app.persistence.identity import SQLIdentityRepository, SQLMembershipRepository
from app.persistence.mapping_repository import SQLMappingRepository
from app.persistence.models import (
    CatalogControlIndexRecord,
    MappingCollectionRecord,
    MappingMemberRecord,
    ProfileRecord,
)
from app.persistence.profile_repository import SQLProfileRepository
from app.persistence.repositories import SQLAlchemyUnitOfWork

pytestmark = pytest.mark.integration
EXAMPLES = Path(__file__).parents[3] / "examples" / "catalogs"


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


def _create_actor(session_factory, tenant_id: UUID):
    with session_factory.begin() as session:
        identity = SQLIdentityRepository(session).get_or_create(
            issuer="https://issuer.example.test",
            subject=f"pm-concurrency-{uuid4()}",
            display_name="Profile/Mapping Concurrency Tester",
            email=None,
        )
        SQLMembershipRepository(session).assign(
            tenant_id=tenant_id,
            user_id=identity.id,
            role="catalog_editor",
            status="active",
        )
        return identity


def _control_id(session_factory, tenant_id: UUID, revision_id: UUID) -> str:
    with session_factory.begin() as session:
        control_id = session.scalars(
            select(CatalogControlIndexRecord.oscal_control_id)
            .where(
                CatalogControlIndexRecord.tenant_id == tenant_id,
                CatalogControlIndexRecord.catalog_revision_id == revision_id,
            )
            .order_by(CatalogControlIndexRecord.oscal_control_id)
        ).first()
    assert control_id is not None
    return control_id


def _mapping_member_projection(
    session_factory,
    *,
    tenant_id: UUID,
    collection_id: UUID,
) -> list[tuple[str, UUID, UUID, str, str]]:
    with session_factory.begin() as session:
        rows = session.execute(
            select(
                MappingMemberRecord.side,
                MappingMemberRecord.catalog_id,
                MappingMemberRecord.revision_id,
                MappingMemberRecord.control_id,
                MappingMemberRecord.oscal_member_id,
            )
            .where(
                MappingMemberRecord.tenant_id == tenant_id,
                MappingMemberRecord.collection_id == collection_id,
            )
            .order_by(
                MappingMemberRecord.side,
                MappingMemberRecord.catalog_id,
                MappingMemberRecord.revision_id,
                MappingMemberRecord.oscal_member_id,
            )
        ).all()
    return [
        (side, catalog_id, revision_id, control_id or "", member_id)
        for side, catalog_id, revision_id, control_id, member_id in rows
    ]


def _prepare_context(grc_service, session_factory):
    tenant = grc_service.create_tenant("PM service tenant", f"pm-service-{uuid4().hex}")
    actor = _create_actor(session_factory, tenant.id)
    importer = CatalogImportService(lambda: SQLAlchemyUnitOfWork(session_factory))
    source = importer.import_catalog(
        tenant.id,
        (EXAMPLES / "sample-security-practices.json").read_bytes(),
    )
    target = importer.import_catalog(
        tenant.id,
        (EXAMPLES / "sample-data-handling.json").read_bytes(),
    )
    source_control = _control_id(session_factory, tenant.id, source.revision.id)
    target_control = _control_id(session_factory, tenant.id, target.revision.id)
    return {
        "tenant_id": tenant.id,
        "actor": actor,
        "source_catalog_id": source.catalog.id,
        "source_revision_id": source.revision.id,
        "source_control": source_control,
        "target_catalog_id": target.catalog.id,
        "target_revision_id": target.revision.id,
        "target_control": target_control,
    }


def _single_pair(context: dict[str, object]) -> list[MappingPairSpec]:
    return [
        MappingPairSpec(
            id=None,
            source_catalog_id=context["source_catalog_id"],
            source_revision_id=context["source_revision_id"],
            target_catalog_id=context["target_catalog_id"],
            target_revision_id=context["target_revision_id"],
            entries=(
                MappingEntrySpec(
                    id=None,
                    sources=(context["source_control"],),
                    targets=(context["target_control"],),
                    relationship="equivalent-to",
                    matching_rationale="semantic",
                    justification="coverage",
                ),
            ),
        )
    ]


def test_profile_update_uses_pg_blocking_pids_and_rejects_stale_tokens(
    grc_service, session_factory, monkeypatch
) -> None:
    context = _prepare_context(grc_service, session_factory)
    service = ProfileService(lambda: session_factory.begin())
    profile = service.create(
        context["tenant_id"],
        context["source_catalog_id"],
        context["source_revision_id"],
        "Blocking profile",
        [context["source_control"]],
        "Initial",
    )
    token = profile.concurrency_version

    release = threading.Barrier(3)
    winner_holding_lock = threading.Event()
    gate_release = threading.Event()
    state_lock = threading.Lock()
    backend_pids: dict[str, int] = {}
    winner_pid: dict[str, int | None] = {"value": None}
    original_get = SQLProfileRepository.get

    def _gated_get(self, tenant_id, profile_id, *, lock=False):
        loaded = original_get(self, tenant_id, profile_id, lock=lock)
        if lock:
            pid = _backend_pid(self._session)
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

    monkeypatch.setattr(SQLProfileRepository, "get", _gated_get)

    def _attempt(worker: str):
        with session_factory.begin() as thread_session:
            with state_lock:
                backend_pids[worker] = _backend_pid(thread_session)
            concurrent_service = ProfileService(lambda: _bound_scope(thread_session))
            release.wait(timeout=5)
            return concurrent_service.update(
                context["tenant_id"],
                profile.id,
                token,
                f"Winner {worker}",
                [context["source_control"]],
                "Updated",
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
    stale: list[StaleProfileUpdate] = []
    for future in futures:
        try:
            updated.append(future.result())
        except StaleProfileUpdate as error:
            stale.append(error)

    assert len(updated) == 1
    assert len(stale) == 1
    assert stale[0].expected_version == token
    assert stale[0].current_version == token + 1

    persisted = service.get(context["tenant_id"], profile.id)
    assert persisted.concurrency_version == token + 1


def test_profile_mapper_stale_translation_rolls_back_document_imports_and_provenance(
    grc_service, session_factory, monkeypatch
) -> None:
    context = _prepare_context(grc_service, session_factory)
    profile_service = ProfileService(lambda: session_factory.begin())
    implementation_service = ImplementationService(lambda: session_factory.begin())
    profile = profile_service.create(
        context["tenant_id"],
        context["source_catalog_id"],
        context["source_revision_id"],
        "Profile before stale",
        [context["source_control"]],
        "Before",
    )
    original_import = profile.imports[0]

    implementation = implementation_service.create(
        context["tenant_id"],
        context["actor"].id,
        context["source_catalog_id"],
        context["source_revision_id"],
        context["source_control"],
        None,
        profile.id,
        ImplementationInformation(
            "Original provenance",
            ImplementationStatus.IMPLEMENTED,
            [],
            [],
            OscalImplementationStatus.IMPLEMENTED,
            None,
        ),
        profile_import_id=original_import.id,
    )

    before = profile_service.get(context["tenant_id"], profile.id)

    def _stale_update(self, updated_profile):
        record = self._session.scalar(
            select(ProfileRecord).where(
                ProfileRecord.tenant_id == updated_profile.tenant_id,
                ProfileRecord.id == updated_profile.id,
            )
        )
        assert record is not None
        with self._session.no_autoflush:
            self._session.execute(
                text(
                    "UPDATE profiles "
                    "SET concurrency_version = concurrency_version + 1 "
                    "WHERE tenant_id = :tenant_id AND id = :profile_id"
                ),
                {
                    "tenant_id": updated_profile.tenant_id,
                    "profile_id": updated_profile.id,
                },
            )
            record.title = updated_profile.title
            record.document = updated_profile.document
            record.updated_at = updated_profile.updated_at
            self._update_imports(updated_profile)

    monkeypatch.setattr(SQLProfileRepository, "update", _stale_update)

    with pytest.raises(StaleProfileUpdate) as stale:
        profile_service.update(
            context["tenant_id"],
            profile.id,
            before.concurrency_version,
            "Profile after stale",
            None,
            "After",
            imports=[
                ProfileImport(
                    id=original_import.id,
                    catalog_id=original_import.catalog_id,
                    revision_id=original_import.revision_id,
                    control_ids=[context["source_control"]],
                ),
                ProfileImport(
                    id=uuid4(),
                    catalog_id=context["target_catalog_id"],
                    revision_id=context["target_revision_id"],
                    control_ids=[context["target_control"]],
                ),
            ],
        )

    assert isinstance(stale.value.__cause__, StaleDataError)
    assert stale.value.expected_version == before.concurrency_version
    assert stale.value.current_version == before.concurrency_version

    after = profile_service.get(context["tenant_id"], profile.id)
    assert after.title == before.title
    assert after.document == before.document
    assert [item.id for item in after.imports] == [item.id for item in before.imports]
    assert [
        (item.catalog_id, item.revision_id, tuple(item.control_ids)) for item in after.imports
    ] == [
        (item.catalog_id, item.revision_id, tuple(item.control_ids)) for item in before.imports
    ]

    persisted_implementation = implementation_service.get(context["tenant_id"], implementation.id)
    assert persisted_implementation.profile_import_id == original_import.id
    assert persisted_implementation.catalog_id == context["source_catalog_id"]
    assert persisted_implementation.revision_id == context["source_revision_id"]


def test_mapping_update_uses_pg_blocking_pids_and_rejects_stale_tokens(
    grc_service, session_factory, monkeypatch
) -> None:
    context = _prepare_context(grc_service, session_factory)
    service = MappingService(lambda: session_factory.begin())
    collection = service.create(
        context["tenant_id"],
        context["actor"],
        "Blocking mapping",
        "Initial",
        _single_pair(context),
    )
    token = collection.concurrency_version

    release = threading.Barrier(3)
    winner_holding_lock = threading.Event()
    gate_release = threading.Event()
    state_lock = threading.Lock()
    backend_pids: dict[str, int] = {}
    winner_pid: dict[str, int | None] = {"value": None}
    original_get = SQLMappingRepository.get

    def _gated_get(self, tenant_id, collection_id, *, lock=False):
        loaded = original_get(self, tenant_id, collection_id, lock=lock)
        if lock:
            pid = _backend_pid(self._session)
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

    monkeypatch.setattr(SQLMappingRepository, "get", _gated_get)

    def _attempt(worker: str):
        with session_factory.begin() as thread_session:
            with state_lock:
                backend_pids[worker] = _backend_pid(thread_session)
            concurrent_service = MappingService(lambda: _bound_scope(thread_session))
            release.wait(timeout=5)
            return concurrent_service.update(
                context["tenant_id"],
                collection.id,
                token,
                context["actor"],
                f"Mapping {worker}",
                "Updated",
                _single_pair(context),
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
    stale: list[StaleMappingCollectionUpdate] = []
    for future in futures:
        try:
            updated.append(future.result())
        except StaleMappingCollectionUpdate as error:
            stale.append(error)

    assert len(updated) == 1
    assert len(stale) == 1
    assert stale[0].expected_version == token
    assert stale[0].current_version == token + 1

    persisted = service.get(context["tenant_id"], collection.id)
    assert persisted.concurrency_version == token + 1


def test_mapping_mapper_stale_translation_rolls_back_document_and_members(
    grc_service, session_factory, monkeypatch
) -> None:
    context = _prepare_context(grc_service, session_factory)
    service = MappingService(lambda: session_factory.begin())
    collection = service.create(
        context["tenant_id"],
        context["actor"],
        "Before stale",
        "Initial",
        _single_pair(context),
    )
    before = service.get(context["tenant_id"], collection.id)
    before_members = _mapping_member_projection(
        session_factory,
        tenant_id=context["tenant_id"],
        collection_id=collection.id,
    )

    def _stale_update(self, updated_collection, members):
        record = self._session.scalar(
            select(MappingCollectionRecord)
            .where(
                MappingCollectionRecord.tenant_id == updated_collection.tenant_id,
                MappingCollectionRecord.id == updated_collection.id,
            )
            .with_for_update()
        )
        assert record is not None
        with self._session.no_autoflush:
            self._session.execute(
                text(
                    "UPDATE mapping_collections "
                    "SET concurrency_version = concurrency_version + 1 "
                    "WHERE tenant_id = :tenant_id AND id = :collection_id"
                ),
                {
                    "tenant_id": updated_collection.tenant_id,
                    "collection_id": updated_collection.id,
                },
            )
            record.document = updated_collection.document
            record.updated_by = updated_collection.updated_by
            record.updated_at = updated_collection.updated_at
            self._session.query(MappingMemberRecord).filter_by(
                tenant_id=updated_collection.tenant_id,
                collection_id=updated_collection.id,
            ).delete(synchronize_session=False)
            self._session.add_all(members)

    monkeypatch.setattr(SQLMappingRepository, "update", _stale_update)

    with pytest.raises(StaleMappingCollectionUpdate) as stale:
        service.update(
            context["tenant_id"],
            collection.id,
            before.concurrency_version,
            context["actor"],
            "After stale",
            "Updated",
            [
                MappingPairSpec(
                    id=None,
                    source_catalog_id=context["source_catalog_id"],
                    source_revision_id=context["source_revision_id"],
                    target_catalog_id=context["target_catalog_id"],
                    target_revision_id=context["target_revision_id"],
                    entries=(
                        MappingEntrySpec(
                            id=None,
                            sources=(context["source_control"],),
                            targets=(context["target_control"],),
                            relationship="subset-of",
                            matching_rationale="functional",
                            justification="changed",
                        ),
                    ),
                )
            ],
        )

    assert isinstance(stale.value.__cause__, StaleDataError)
    assert stale.value.expected_version == before.concurrency_version
    assert stale.value.current_version == before.concurrency_version

    after = service.get(context["tenant_id"], collection.id)
    after_members = _mapping_member_projection(
        session_factory,
        tenant_id=context["tenant_id"],
        collection_id=collection.id,
    )
    assert after.document == before.document
    assert after_members == before_members


def test_mapping_stale_delete_preserves_member_projection_and_revision_pinning(
    grc_service, session_factory
) -> None:
    context = _prepare_context(grc_service, session_factory)
    service = MappingService(lambda: session_factory.begin())
    collection = service.create(
        context["tenant_id"],
        context["actor"],
        "Delete stale",
        "Initial",
        _single_pair(context),
    )
    token = collection.concurrency_version

    updated = service.update(
        context["tenant_id"],
        collection.id,
        token,
        context["actor"],
        "Delete stale updated",
        "Initial",
        _single_pair(context),
    )
    members_before_stale_delete = _mapping_member_projection(
        session_factory,
        tenant_id=context["tenant_id"],
        collection_id=collection.id,
    )

    with pytest.raises(StaleMappingCollectionUpdate) as stale:
        service.delete(context["tenant_id"], collection.id, expected_version=token)

    assert stale.value.expected_version == token
    assert stale.value.current_version == updated.concurrency_version

    persisted = service.get(context["tenant_id"], collection.id)
    members_after_stale_delete = _mapping_member_projection(
        session_factory,
        tenant_id=context["tenant_id"],
        collection_id=collection.id,
    )
    assert members_after_stale_delete == members_before_stale_delete

    mapping = persisted.document["mapping-collection"]["mappings"][0]
    assert str(context["source_revision_id"]) in mapping["source-resource"]["href"]
    assert str(context["target_revision_id"]) in mapping["target-resource"]["href"]

