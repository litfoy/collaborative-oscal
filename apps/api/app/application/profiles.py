from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from uuid import UUID, uuid4

from collaborative_oscal_oscal.profile import build_profile_document
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.catalogs.read_models import Page
from app.domain.errors import EntityNotFoundError
from app.domain.profiles.models import Profile
from app.persistence.models import CatalogControlIndexRecord, CatalogRevisionRecord
from app.persistence.profile_repository import SQLProfileRepository

SessionScope = Callable[[], AbstractContextManager[Session]]


class InvalidProfileSelection(ValueError):
    pass


class ProfileService:
    def __init__(self, session_scope: SessionScope) -> None:
        self._session_scope = session_scope

    def create(
        self,
        tenant_id: UUID,
        catalog_id: UUID,
        revision_id: UUID,
        title: str,
        control_ids: Sequence[str],
    ) -> Profile:
        now = datetime.now(UTC)
        profile_id = uuid4()
        with self._session_scope() as session:
            revision = self._get_revision(session, tenant_id, catalog_id, revision_id)
            self._validate_control_ids(session, tenant_id, revision_id, control_ids)
            document = build_profile_document(
                profile_uuid=uuid4(),
                title=title,
                oscal_version=revision.oscal_version,
                catalog_href=self._catalog_href(tenant_id, catalog_id, revision_id),
                control_ids=control_ids,
                last_modified=now,
            )
            profile = Profile(
                profile_id,
                tenant_id,
                catalog_id,
                revision_id,
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
        self, tenant_id: UUID, profile_id: UUID, title: str, control_ids: Sequence[str]
    ) -> Profile:
        now = datetime.now(UTC)
        with self._session_scope() as session:
            repository = SQLProfileRepository(session)
            existing = repository.get(tenant_id, profile_id)
            if existing is None:
                raise EntityNotFoundError("Profile not found.")
            revision = self._get_revision(
                session, tenant_id, existing.catalog_id, existing.revision_id
            )
            self._validate_control_ids(session, tenant_id, existing.revision_id, control_ids)
            metadata = existing.document["profile"]["metadata"]
            document = build_profile_document(
                profile_uuid=UUID(existing.document["profile"]["uuid"]),
                title=title,
                oscal_version=revision.oscal_version,
                catalog_href=self._catalog_href(
                    tenant_id, existing.catalog_id, existing.revision_id
                ),
                control_ids=control_ids,
                version=metadata["version"],
                last_modified=now,
            )
            updated = Profile(
                existing.id,
                existing.tenant_id,
                existing.catalog_id,
                existing.revision_id,
                title,
                document,
                existing.created_at,
                now,
            )
            repository.update(updated)
        return updated

    @staticmethod
    def _get_revision(
        session: Session, tenant_id: UUID, catalog_id: UUID, revision_id: UUID
    ) -> CatalogRevisionRecord:
        revision = session.scalar(
            select(CatalogRevisionRecord).where(
                CatalogRevisionRecord.tenant_id == tenant_id,
                CatalogRevisionRecord.catalog_id == catalog_id,
                CatalogRevisionRecord.id == revision_id,
            )
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
