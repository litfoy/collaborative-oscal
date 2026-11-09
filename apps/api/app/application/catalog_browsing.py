from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from collaborative_oscal_oscal.control_view import (
    collect_link_resource_ids,
    project_control,
    project_resource,
)
from sqlalchemy.orm import Session

from app.domain.catalogs.models import CatalogRevisionStatus
from app.domain.catalogs.read_models import (
    CatalogSummary,
    ControlListItem,
    ControlRecordView,
    OutlineNode,
    OutlineNodeKind,
    Page,
    RevisionDetail,
    RevisionSummary,
)
from app.domain.errors import EntityNotFoundError
from app.persistence.catalog_queries import SQLCatalogQueryRepository

SessionScope = Callable[[], AbstractContextManager[Session]]


@dataclass(frozen=True, slots=True)
class ControlDetailView:
    record: ControlRecordView
    content: dict[str, Any]
    resources: list[dict[str, Any]]
    catalog: CatalogSummary
    revision: RevisionDetail


class CatalogBrowsingService:
    """Read-only catalog browsing for an already authorized tenant.

    `tenant_id` must come from an `AuthorizedTenantContext`. Resources outside the
    tenant are indistinguishable from nonexistent resources.
    """

    def __init__(self, session_scope: SessionScope) -> None:
        self._session_scope = session_scope

    def list_catalogs(
        self, tenant_id: UUID, *, query: str | None, limit: int, offset: int
    ) -> Page[CatalogSummary]:
        with self._session_scope() as session:
            return SQLCatalogQueryRepository(session).list_catalogs(
                tenant_id, query=query, limit=limit, offset=offset
            )

    def get_catalog(self, tenant_id: UUID, catalog_id: UUID) -> CatalogSummary:
        with self._session_scope() as session:
            catalog = SQLCatalogQueryRepository(session).get_catalog(tenant_id, catalog_id)
        if catalog is None:
            raise EntityNotFoundError("Catalog not found.")
        return catalog

    def list_revisions(
        self,
        tenant_id: UUID,
        catalog_id: UUID,
        *,
        status: CatalogRevisionStatus | None,
        limit: int,
        offset: int,
    ) -> Page[RevisionSummary]:
        with self._session_scope() as session:
            repository = SQLCatalogQueryRepository(session)
            if repository.get_catalog(tenant_id, catalog_id) is None:
                raise EntityNotFoundError("Catalog not found.")
            return repository.list_revisions(
                tenant_id, catalog_id, status=status, limit=limit, offset=offset
            )

    def get_revision(self, tenant_id: UUID, catalog_id: UUID, revision_id: UUID) -> RevisionDetail:
        with self._session_scope() as session:
            revision = SQLCatalogQueryRepository(session).get_revision(
                tenant_id, catalog_id, revision_id
            )
        if revision is None:
            raise EntityNotFoundError("Catalog revision not found.")
        return revision

    def list_outline(
        self,
        tenant_id: UUID,
        catalog_id: UUID,
        revision_id: UUID,
        *,
        parent_kind: OutlineNodeKind | None,
        parent_id: UUID | None,
        limit: int,
        offset: int,
    ) -> Page[OutlineNode]:
        with self._session_scope() as session:
            repository = SQLCatalogQueryRepository(session)
            if not repository.revision_exists(tenant_id, catalog_id, revision_id):
                raise EntityNotFoundError("Catalog revision not found.")
            if parent_id is not None and parent_kind is not None:
                if not repository.outline_parent_exists(
                    tenant_id, revision_id, parent_kind, parent_id
                ):
                    raise EntityNotFoundError("Outline parent not found.")
            return repository.list_outline(
                tenant_id,
                revision_id,
                parent_kind=parent_kind,
                parent_id=parent_id,
                limit=limit,
                offset=offset,
            )

    def search_controls(
        self,
        tenant_id: UUID,
        catalog_id: UUID,
        revision_id: UUID,
        *,
        query: str | None,
        limit: int,
        offset: int,
    ) -> Page[ControlListItem]:
        with self._session_scope() as session:
            repository = SQLCatalogQueryRepository(session)
            if not repository.revision_exists(tenant_id, catalog_id, revision_id):
                raise EntityNotFoundError("Catalog revision not found.")
            return repository.search_controls(
                tenant_id, revision_id, query=query, limit=limit, offset=offset
            )

    def get_control(
        self,
        tenant_id: UUID,
        catalog_id: UUID,
        revision_id: UUID,
        oscal_control_id: str,
    ) -> ControlDetailView:
        with self._session_scope() as session:
            repository = SQLCatalogQueryRepository(session)
            catalog = repository.get_catalog(tenant_id, catalog_id)
            revision = repository.get_revision(tenant_id, catalog_id, revision_id)
            if catalog is None or revision is None:
                raise EntityNotFoundError("Catalog revision not found.")
            record = repository.get_control(tenant_id, revision_id, oscal_control_id)
            if record is None:
                raise EntityNotFoundError("Control not found.")
            content = project_control(record.raw_control)
            resources = [
                projected
                for projected in (
                    project_resource(item)
                    for item in repository.get_resources(
                        tenant_id, revision_id, collect_link_resource_ids(content)
                    )
                )
                if projected is not None
            ]
        return ControlDetailView(record, content, resources, catalog, revision)
