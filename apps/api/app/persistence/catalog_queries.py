"""Read-only, tenant-scoped catalog queries.

Every query filters on `tenant_id`; callers must pass a tenant id obtained from a
verified `AuthorizedTenantContext`. Queries select explicit columns so that the
authoritative OSCAL JSONB document is only read when a control or metadata slice
is requested, and then only through a JSONB path expression.
"""

from __future__ import annotations

import json
from uuid import UUID

from collaborative_oscal_oscal.control_view import (
    ancestor_structural_paths,
    jsonb_path_for_structural_path,
)
from sqlalchemy import (
    Integer,
    and_,
    case,
    cast,
    func,
    literal,
    or_,
    select,
    union_all,
)
from sqlalchemy.dialects.postgresql import JSONB, distinct_on
from sqlalchemy.orm import Session, aliased
from sqlalchemy.types import UserDefinedType

from app.domain.catalogs.models import CatalogRevisionStatus
from app.domain.catalogs.read_models import (
    AncestorRef,
    CatalogSummary,
    ControlListItem,
    ControlRecordView,
    GroupRef,
    OutlineNode,
    OutlineNodeKind,
    Page,
    RevisionDetail,
    RevisionDocumentMetadata,
    RevisionSummary,
)
from app.persistence.models import (
    CatalogControlIndexRecord,
    CatalogGroupIndexRecord,
    CatalogRecord,
    CatalogRevisionRecord,
)


class _JsonPath(UserDefinedType):
    cache_ok = True

    def get_col_spec(self, **kwargs: object) -> str:
        return "jsonpath"


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class SQLCatalogQueryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # Catalogs and revisions

    def list_catalogs(
        self, tenant_id: UUID, *, query: str | None, limit: int, offset: int
    ) -> Page[CatalogSummary]:
        conditions = [CatalogRecord.tenant_id == tenant_id]
        if query:
            pattern = f"%{escape_like(query)}%"
            conditions.append(
                or_(
                    CatalogRecord.name.ilike(pattern, escape="\\"),
                    CatalogRecord.description.ilike(pattern, escape="\\"),
                    CatalogRecord.source_organization.ilike(pattern, escape="\\"),
                )
            )
        total = self._session.scalar(
            select(func.count()).select_from(CatalogRecord).where(*conditions)
        )
        records = self._session.scalars(
            select(CatalogRecord)
            .where(*conditions)
            .order_by(func.lower(CatalogRecord.name), CatalogRecord.id)
            .limit(limit)
            .offset(offset)
        ).all()
        return Page(self._summaries(tenant_id, list(records)), total or 0, limit, offset)

    def get_catalog(self, tenant_id: UUID, catalog_id: UUID) -> CatalogSummary | None:
        record = self._session.scalar(
            select(CatalogRecord).where(
                CatalogRecord.tenant_id == tenant_id, CatalogRecord.id == catalog_id
            )
        )
        if record is None:
            return None
        return self._summaries(tenant_id, [record])[0]

    def _summaries(self, tenant_id: UUID, records: list[CatalogRecord]) -> list[CatalogSummary]:
        if not records:
            return []
        catalog_ids = [record.id for record in records]
        counts = dict(
            self._session.execute(
                select(CatalogRevisionRecord.catalog_id, func.count())
                .where(
                    CatalogRevisionRecord.tenant_id == tenant_id,
                    CatalogRevisionRecord.catalog_id.in_(catalog_ids),
                )
                .group_by(CatalogRevisionRecord.catalog_id)
            ).all()
        )
        latest_rows = self._session.execute(
            self._revision_columns()
            .where(
                CatalogRevisionRecord.tenant_id == tenant_id,
                CatalogRevisionRecord.catalog_id.in_(catalog_ids),
            )
            .ext(distinct_on(CatalogRevisionRecord.catalog_id))
            .order_by(
                CatalogRevisionRecord.catalog_id, CatalogRevisionRecord.revision_number.desc()
            )
        ).all()
        latest = {row.catalog_id: row for row in latest_rows}
        control_counts = self._control_counts(tenant_id, [row.id for row in latest_rows])
        return [
            CatalogSummary(
                id=record.id,
                name=record.name,
                description=record.description,
                origin_type=record.origin_type,
                source_uri=record.source_uri,
                source_organization=record.source_organization,
                license_identifier=record.license_identifier,
                revision_count=counts.get(record.id, 0),
                latest_revision=(
                    self._to_summary(latest[record.id], control_counts)
                    if record.id in latest
                    else None
                ),
            )
            for record in records
        ]

    @staticmethod
    def _revision_columns():
        revision = CatalogRevisionRecord
        return select(
            revision.id,
            revision.catalog_id,
            revision.revision_number,
            revision.lifecycle_status,
            revision.oscal_document_uuid,
            revision.oscal_version,
            revision.source_version,
            revision.source_format,
            revision.created_at,
            revision.published_at,
        )

    def _control_counts(self, tenant_id: UUID, revision_ids: list[UUID]) -> dict[UUID, int]:
        if not revision_ids:
            return {}
        return dict(
            self._session.execute(
                select(CatalogControlIndexRecord.catalog_revision_id, func.count())
                .where(
                    CatalogControlIndexRecord.tenant_id == tenant_id,
                    CatalogControlIndexRecord.catalog_revision_id.in_(revision_ids),
                )
                .group_by(CatalogControlIndexRecord.catalog_revision_id)
            ).all()
        )

    @staticmethod
    def _to_summary(row, control_counts: dict[UUID, int]) -> RevisionSummary:
        return RevisionSummary(
            id=row.id,
            catalog_id=row.catalog_id,
            revision_number=row.revision_number,
            lifecycle_status=CatalogRevisionStatus(row.lifecycle_status),
            oscal_document_uuid=row.oscal_document_uuid,
            oscal_version=row.oscal_version,
            source_version=row.source_version,
            source_format=row.source_format,
            created_at=row.created_at,
            published_at=row.published_at,
            control_count=control_counts.get(row.id, 0),
        )

    def list_revisions(
        self,
        tenant_id: UUID,
        catalog_id: UUID,
        *,
        status: CatalogRevisionStatus | None,
        limit: int,
        offset: int,
    ) -> Page[RevisionSummary]:
        conditions = [
            CatalogRevisionRecord.tenant_id == tenant_id,
            CatalogRevisionRecord.catalog_id == catalog_id,
        ]
        if status is not None:
            conditions.append(CatalogRevisionRecord.lifecycle_status == status.value)
        total = self._session.scalar(
            select(func.count()).select_from(CatalogRevisionRecord).where(*conditions)
        )
        rows = self._session.execute(
            self._revision_columns()
            .where(*conditions)
            .order_by(CatalogRevisionRecord.revision_number.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        counts = self._control_counts(tenant_id, [row.id for row in rows])
        return Page([self._to_summary(row, counts) for row in rows], total or 0, limit, offset)

    def get_revision(
        self, tenant_id: UUID, catalog_id: UUID, revision_id: UUID
    ) -> RevisionDetail | None:
        content = CatalogRevisionRecord.content
        row = self._session.execute(
            self._revision_columns()
            .add_columns(
                content[("catalog", "metadata", "title")].astext.label("doc_title"),
                content[("catalog", "metadata", "version")].astext.label("doc_version"),
                content[("catalog", "metadata", "last-modified")].astext.label("doc_modified"),
                content[("catalog", "metadata", "published")].astext.label("doc_published"),
            )
            .where(
                CatalogRevisionRecord.tenant_id == tenant_id,
                CatalogRevisionRecord.catalog_id == catalog_id,
                CatalogRevisionRecord.id == revision_id,
            )
        ).one_or_none()
        if row is None:
            return None
        group_count = self._session.scalar(
            select(func.count())
            .select_from(CatalogGroupIndexRecord)
            .where(
                CatalogGroupIndexRecord.tenant_id == tenant_id,
                CatalogGroupIndexRecord.catalog_revision_id == revision_id,
            )
        )
        return RevisionDetail(
            summary=self._to_summary(row, self._control_counts(tenant_id, [row.id])),
            group_count=group_count or 0,
            document=RevisionDocumentMetadata(
                title=row.doc_title,
                version=row.doc_version,
                last_modified=row.doc_modified,
                published=row.doc_published,
            ),
        )

    def get_revision_document(
        self, tenant_id: UUID, catalog_id: UUID, revision_id: UUID
    ) -> dict | None:
        return self._session.scalar(
            select(CatalogRevisionRecord.content).where(
                CatalogRevisionRecord.tenant_id == tenant_id,
                CatalogRevisionRecord.catalog_id == catalog_id,
                CatalogRevisionRecord.id == revision_id,
            )
        )

    def revision_exists(self, tenant_id: UUID, catalog_id: UUID, revision_id: UUID) -> bool:
        return (
            self._session.scalar(
                select(CatalogRevisionRecord.id).where(
                    CatalogRevisionRecord.tenant_id == tenant_id,
                    CatalogRevisionRecord.catalog_id == catalog_id,
                    CatalogRevisionRecord.id == revision_id,
                )
            )
            is not None
        )

    # Hierarchy

    def outline_parent_exists(
        self,
        tenant_id: UUID,
        revision_id: UUID,
        kind: OutlineNodeKind,
        node_id: UUID,
    ) -> bool:
        if kind is OutlineNodeKind.GROUP:
            table = CatalogGroupIndexRecord
        else:
            table = CatalogControlIndexRecord
        return (
            self._session.scalar(
                select(table.id).where(
                    table.tenant_id == tenant_id,
                    table.catalog_revision_id == revision_id,
                    table.id == node_id,
                )
            )
            is not None
        )

    def list_outline(
        self,
        tenant_id: UUID,
        revision_id: UUID,
        *,
        parent_kind: OutlineNodeKind | None,
        parent_id: UUID | None,
        limit: int,
        offset: int,
    ) -> Page[OutlineNode]:
        control = CatalogControlIndexRecord
        group = CatalogGroupIndexRecord
        child_control = aliased(CatalogControlIndexRecord)
        top_control = aliased(CatalogControlIndexRecord)
        child_group = aliased(CatalogGroupIndexRecord)
        scope_control = [control.tenant_id == tenant_id, control.catalog_revision_id == revision_id]
        scope_group = [group.tenant_id == tenant_id, group.catalog_revision_id == revision_id]

        controls_of_control = (
            select(func.count())
            .where(
                child_control.tenant_id == tenant_id,
                child_control.catalog_revision_id == revision_id,
                child_control.parent_control_id == control.id,
            )
            .scalar_subquery()
        )
        group_controls = (
            select(func.count())
            .where(
                top_control.tenant_id == tenant_id,
                top_control.catalog_revision_id == revision_id,
                top_control.group_id == group.id,
                top_control.parent_control_id.is_(None),
            )
            .scalar_subquery()
        )
        group_groups = (
            select(func.count())
            .where(
                child_group.tenant_id == tenant_id,
                child_group.catalog_revision_id == revision_id,
                child_group.parent_group_id == group.id,
            )
            .scalar_subquery()
        )

        if parent_kind is None:
            control_filter = [control.group_id.is_(None), control.parent_control_id.is_(None)]
            group_filter: list = [group.parent_group_id.is_(None)]
        elif parent_kind is OutlineNodeKind.GROUP:
            control_filter = [control.group_id == parent_id, control.parent_control_id.is_(None)]
            group_filter = [group.parent_group_id == parent_id]
        else:
            control_filter = [control.parent_control_id == parent_id]
            group_filter = [literal(False)]

        controls_select = select(
            literal(0).label("rank"),
            literal(OutlineNodeKind.CONTROL.value).label("kind"),
            control.id.label("node_id"),
            control.oscal_control_id.label("oscal_id"),
            control.title.label("title"),
            control.display_order.label("display_order"),
            cast(controls_of_control, Integer).label("child_count"),
        ).where(*scope_control, *control_filter)
        groups_select = select(
            literal(1).label("rank"),
            literal(OutlineNodeKind.GROUP.value).label("kind"),
            group.id.label("node_id"),
            group.oscal_group_id.label("oscal_id"),
            group.title.label("title"),
            group.display_order.label("display_order"),
            cast(group_controls + group_groups, Integer).label("child_count"),
        ).where(*scope_group, *group_filter)

        combined = union_all(controls_select, groups_select).subquery()
        rows = self._session.execute(
            select(combined)
            .order_by(combined.c.rank, combined.c.display_order, combined.c.node_id)
            .limit(limit)
            .offset(offset)
        ).all()
        total = self._session.scalar(select(func.count()).select_from(combined))
        return Page(
            [
                OutlineNode(
                    kind=OutlineNodeKind(row.kind),
                    id=row.node_id,
                    oscal_id=row.oscal_id,
                    title=row.title,
                    child_count=row.child_count,
                )
                for row in rows
            ],
            total or 0,
            limit,
            offset,
        )

    # Controls

    def search_controls(
        self,
        tenant_id: UUID,
        revision_id: UUID,
        *,
        query: str | None,
        limit: int,
        offset: int,
    ) -> Page[ControlListItem]:
        control = CatalogControlIndexRecord
        group = CatalogGroupIndexRecord
        conditions = [control.tenant_id == tenant_id, control.catalog_revision_id == revision_id]
        order = [func.lower(control.oscal_control_id), control.id]
        if query:
            pattern = f"%{escape_like(query)}%"
            conditions.append(
                or_(
                    control.oscal_control_id.ilike(pattern, escape="\\"),
                    control.title.ilike(pattern, escape="\\"),
                )
            )
            relevance = case(
                (func.lower(control.oscal_control_id) == query.lower(), 0),
                (
                    control.oscal_control_id.ilike(f"{escape_like(query)}%", escape="\\"),
                    1,
                ),
                else_=2,
            )
            order = [relevance, *order]
        total = self._session.scalar(select(func.count()).select_from(control).where(*conditions))
        rows = self._session.execute(
            select(
                control.id,
                control.oscal_control_id,
                control.title,
                control.parent_control_id,
                group.id.label("group_id"),
                group.oscal_group_id,
                group.title.label("group_title"),
            )
            .outerjoin(
                group,
                and_(
                    group.tenant_id == control.tenant_id,
                    group.catalog_revision_id == control.catalog_revision_id,
                    group.id == control.group_id,
                ),
            )
            .where(*conditions)
            .order_by(*order)
            .limit(limit)
            .offset(offset)
        ).all()
        return Page(
            [
                ControlListItem(
                    id=row.id,
                    oscal_control_id=row.oscal_control_id,
                    title=row.title,
                    parent_control_id=row.parent_control_id,
                    group=(
                        GroupRef(row.group_id, row.oscal_group_id, row.group_title)
                        if row.group_id is not None
                        else None
                    ),
                )
                for row in rows
            ],
            total or 0,
            limit,
            offset,
        )

    def get_control(
        self, tenant_id: UUID, revision_id: UUID, oscal_control_id: str
    ) -> ControlRecordView | None:
        control = CatalogControlIndexRecord
        group = CatalogGroupIndexRecord
        row = self._session.execute(
            select(
                control.id,
                control.oscal_control_id,
                control.title,
                control.structural_path,
                control.parent_control_id,
                group.id.label("group_id"),
                group.oscal_group_id,
                group.title.label("group_title"),
            )
            .outerjoin(
                group,
                and_(
                    group.tenant_id == control.tenant_id,
                    group.catalog_revision_id == control.catalog_revision_id,
                    group.id == control.group_id,
                ),
            )
            .where(
                control.tenant_id == tenant_id,
                control.catalog_revision_id == revision_id,
                control.oscal_control_id == oscal_control_id,
            )
        ).one_or_none()
        if row is None:
            return None

        document_path = jsonb_path_for_structural_path(row.structural_path)
        raw_control = self._session.scalar(
            select(CatalogRevisionRecord.content[tuple(document_path)]).where(
                CatalogRevisionRecord.tenant_id == tenant_id,
                CatalogRevisionRecord.id == revision_id,
            )
        )
        if not isinstance(raw_control, dict) or raw_control.get("id") != row.oscal_control_id:
            raise RuntimeError("Control index does not match its stored OSCAL document.")

        child_count = self._session.scalar(
            select(func.count())
            .select_from(control)
            .where(
                control.tenant_id == tenant_id,
                control.catalog_revision_id == revision_id,
                control.parent_control_id == row.id,
            )
        )
        return ControlRecordView(
            id=row.id,
            oscal_control_id=row.oscal_control_id,
            title=row.title,
            structural_path=row.structural_path,
            parent_control_id=row.parent_control_id,
            group=(
                GroupRef(row.group_id, row.oscal_group_id, row.group_title)
                if row.group_id is not None
                else None
            ),
            ancestors=self._ancestors(tenant_id, revision_id, row.structural_path),
            child_control_count=child_count or 0,
            raw_control=raw_control,
            resources=[],
        )

    def _ancestors(
        self, tenant_id: UUID, revision_id: UUID, structural_path: str
    ) -> list[AncestorRef]:
        paths = ancestor_structural_paths(structural_path)
        if not paths:
            return []
        control = CatalogControlIndexRecord
        group = CatalogGroupIndexRecord
        found: dict[str, AncestorRef] = {}
        for row in self._session.execute(
            select(group.structural_path, group.id, group.oscal_group_id, group.title).where(
                group.tenant_id == tenant_id,
                group.catalog_revision_id == revision_id,
                group.structural_path.in_(paths),
            )
        ):
            found[row.structural_path] = AncestorRef(
                OutlineNodeKind.GROUP, row.id, row.oscal_group_id, row.title
            )
        for row in self._session.execute(
            select(
                control.structural_path, control.id, control.oscal_control_id, control.title
            ).where(
                control.tenant_id == tenant_id,
                control.catalog_revision_id == revision_id,
                control.structural_path.in_(paths),
            )
        ):
            found[row.structural_path] = AncestorRef(
                OutlineNodeKind.CONTROL, row.id, row.oscal_control_id, row.title
            )
        return [found[path] for path in paths if path in found]

    def get_resources(
        self, tenant_id: UUID, revision_id: UUID, resource_ids: list[str]
    ) -> list[dict]:
        if not resource_ids:
            return []
        resources = CatalogRevisionRecord.content[("catalog", "back-matter", "resources")]
        selected = self._session.scalar(
            select(
                func.jsonb_path_query_array(
                    resources,
                    cast(literal("$[*] ? (@.uuid == $ids[*])"), _JsonPath()),
                    cast(literal(json.dumps({"ids": resource_ids})), JSONB),
                )
            ).where(
                CatalogRevisionRecord.tenant_id == tenant_id,
                CatalogRevisionRecord.id == revision_id,
                resources.is_not(None),
            )
        )
        return [item for item in selected or [] if isinstance(item, dict)]
