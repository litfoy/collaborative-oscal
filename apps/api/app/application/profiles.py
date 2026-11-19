# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from uuid import UUID, uuid4

from collaborative_oscal_oscal.profile import build_profile_document
from collaborative_oscal_oscal.versions import DEFAULT_OSCAL_VERSION
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.domain.catalogs.read_models import Page
from app.domain.errors import EntityNotFoundError
from app.domain.profiles.models import Profile, ProfileImport
from app.persistence.models import (
    CatalogControlIndexRecord,
    CatalogRevisionRecord,
    ProfileImportRecord,
    ProfileRecord,
)
from app.persistence.profile_repository import SQLProfileRepository

SessionScope = Callable[[], AbstractContextManager[Session]]


class InvalidProfileSelection(ValueError):
    pass


class StaleProfileUpdate(ValueError):
    def __init__(self, profile_id: UUID, expected_version: int, current_version: int) -> None:
        self.profile_id = profile_id
        self.expected_version = expected_version
        self.current_version = current_version
        super().__init__("The Profile changed after it was loaded.")


class _StaleProfileFlush(RuntimeError):
    def __init__(self, profile_id: UUID, expected_version: int) -> None:
        self.profile_id = profile_id
        self.expected_version = expected_version
        super().__init__("Profile flush detected stale mapper version.")


class ProfileService:
    def __init__(self, session_scope: SessionScope) -> None:
        self._session_scope = session_scope

    def create(
        self,
        tenant_id: UUID,
        catalog_id: UUID | None,
        revision_id: UUID | None,
        title: str,
        control_ids: Sequence[str] | None,
        description: str = "",
        imports: Sequence[ProfileImport] | None = None,
        oscal_version: str | None = None,
    ) -> Profile:
        now = datetime.now(UTC)
        profile_id = uuid4()
        with self._session_scope() as session:
            if imports is None:
                if catalog_id is None or revision_id is None or control_ids is None:
                    raise InvalidProfileSelection("A catalog source is required.")
                imports = [ProfileImport(uuid4(), catalog_id, revision_id, list(control_ids))]
            self._validate_import_identities(session, imports, None)
            self._validate_imports(session, tenant_id, imports)
            document = build_profile_document(
                profile_uuid=uuid4(),
                title=title,
                oscal_version=(
                    DEFAULT_OSCAL_VERSION if oscal_version is None else oscal_version
                ),
                imports=[
                    (
                        self._catalog_href(tenant_id, item.catalog_id, item.revision_id),
                        item.control_ids,
                    )
                    for item in imports
                ],
                last_modified=now,
                description=description,
            )
            profile = Profile(
                profile_id,
                tenant_id,
                list(imports),
                title,
                document,
                now,
                now,
            )
            SQLProfileRepository(session).add(profile)
        return profile

    def get(self, tenant_id: UUID, profile_id: UUID) -> Profile:
        with self._session_scope() as session:
            profile = SQLProfileRepository(session).get(tenant_id, profile_id)
        if profile is None:
            raise EntityNotFoundError("Profile not found.")
        return profile

    def list(self, tenant_id: UUID, *, limit: int, offset: int) -> Page[Profile]:
        with self._session_scope() as session:
            return SQLProfileRepository(session).list_for_tenant(
                tenant_id, limit=limit, offset=offset
            )

    def update(
        self,
        tenant_id: UUID,
        profile_id: UUID,
        expected_version: int,
        title: str,
        control_ids: Sequence[str] | None,
        description: str | None = None,
        imports: Sequence[ProfileImport] | None = None,
    ) -> Profile:
        try:
            with self._session_scope() as session:
                repository = SQLProfileRepository(session)
                existing = repository.get(tenant_id, profile_id, lock=True)
                if existing is None:
                    raise EntityNotFoundError("Profile not found.")
                if existing.concurrency_version != expected_version:
                    raise StaleProfileUpdate(
                        existing.id,
                        expected_version,
                        existing.concurrency_version,
                    )
                if imports is None:
                    if len(existing.imports) != 1 or control_ids is None:
                        raise InvalidProfileSelection(
                            "Multi-import profiles require imports in updates."
                        )
                    old = existing.imports[0]
                    imports = [
                        ProfileImport(old.id, old.catalog_id, old.revision_id, list(control_ids))
                    ]
                existing_by_id = {item.id: item for item in existing.imports}
                for item in imports:
                    old = existing_by_id.get(item.id)
                    if old and (old.catalog_id, old.revision_id) != (
                        item.catalog_id,
                        item.revision_id,
                    ):
                        raise InvalidProfileSelection(
                            "An existing import cannot change its source."
                        )
                self._validate_import_identities(session, imports, profile_id)
                self._validate_imports(session, tenant_id, imports)
                now = datetime.now(UTC)
                metadata = existing.document["profile"]["metadata"]
                document = build_profile_document(
                    profile_uuid=uuid4(),
                    title=title,
                    oscal_version=metadata["oscal-version"],
                    imports=[
                        (
                            self._catalog_href(tenant_id, item.catalog_id, item.revision_id),
                            item.control_ids,
                        )
                        for item in imports
                    ],
                    version=metadata["version"],
                    last_modified=now,
                    description=(
                        description
                        if description is not None
                        else metadata.get("remarks", "")
                    ),
                )
                updated = Profile(
                    existing.id,
                    existing.tenant_id,
                    list(imports),
                    title,
                    document,
                    existing.created_at,
                    now,
                    existing.concurrency_version,
                )
                try:
                    repository.update(updated)
                    session.flush()
                    persisted = repository.get(tenant_id, profile_id)
                    if persisted is None:
                        raise RuntimeError("Profile disappeared after update.")
                    return persisted
                except StaleDataError as error:
                    raise _StaleProfileFlush(profile_id, expected_version) from error
        except _StaleProfileFlush as stale:
            current = self._current_profile_version(tenant_id, stale.profile_id)
            raise StaleProfileUpdate(
                stale.profile_id,
                stale.expected_version,
                current,
            ) from stale.__cause__

    def _current_profile_version(self, tenant_id: UUID, profile_id: UUID) -> int:
        with self._session_scope() as session:
            current = session.scalar(
                select(ProfileRecord.concurrency_version).where(
                    ProfileRecord.tenant_id == tenant_id,
                    ProfileRecord.id == profile_id,
                )
            )
            if current is None:
                raise EntityNotFoundError("Profile not found.")
            return int(current)

    @staticmethod
    def _validate_import_identities(
        session: Session, imports: Sequence[ProfileImport], profile_id: UUID | None
    ) -> None:
        rows = session.scalars(
            select(ProfileImportRecord).where(
                ProfileImportRecord.id.in_([item.id for item in imports])
            )
        ).all()
        supplied = {item.id: item for item in imports}
        for row in rows:
            item = supplied[row.id]
            if row.profile_id != profile_id or (row.catalog_id, row.revision_id) != (
                item.catalog_id,
                item.revision_id,
            ):
                raise InvalidProfileSelection("Profile import identity or source is invalid.")

    @staticmethod
    def _validate_imports(
        session: Session, tenant_id: UUID, imports: Sequence[ProfileImport]
    ) -> None:
        if not imports or len({item.id for item in imports}) != len(imports):
            raise InvalidProfileSelection("Profile imports must have distinct identities.")
        for item in sorted(imports, key=lambda source: source.revision_id):
            ProfileService._get_revision(
                session, tenant_id, item.catalog_id, item.revision_id
            )
            ProfileService._validate_control_ids(
                session, tenant_id, item.revision_id, item.control_ids
            )

    @staticmethod
    def _get_revision(
        session: Session, tenant_id: UUID, catalog_id: UUID, revision_id: UUID
    ) -> CatalogRevisionRecord:
        revision = session.scalar(
            select(CatalogRevisionRecord)
            .where(
                CatalogRevisionRecord.tenant_id == tenant_id,
                CatalogRevisionRecord.catalog_id == catalog_id,
                CatalogRevisionRecord.id == revision_id,
            )
            .with_for_update()
        )
        if revision is None:
            raise EntityNotFoundError("Catalog revision not found.")
        return revision

    @staticmethod
    def _validate_control_ids(
        session: Session, tenant_id: UUID, revision_id: UUID, control_ids: Sequence[str]
    ) -> None:
        existing_ids = set(
            session.scalars(
                select(CatalogControlIndexRecord.oscal_control_id).where(
                    CatalogControlIndexRecord.tenant_id == tenant_id,
                    CatalogControlIndexRecord.catalog_revision_id == revision_id,
                    CatalogControlIndexRecord.oscal_control_id.in_(control_ids),
                )
            )
        )
        if missing := set(control_ids) - existing_ids:
            raise InvalidProfileSelection(
                "Selected controls do not exist in the referenced catalog revision: "
                + ", ".join(sorted(missing))
            )

    @staticmethod
    def _catalog_href(tenant_id: UUID, catalog_id: UUID, revision_id: UUID) -> str:
        return f"/api/v1/tenants/{tenant_id}/catalogs/{catalog_id}/revisions/{revision_id}/export"