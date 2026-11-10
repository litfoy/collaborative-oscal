from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.application.catalog_browsing import ControlDetailView
from app.domain.catalogs.models import CatalogRevisionStatus
from app.domain.catalogs.read_models import (
    CatalogSummary,
    ControlListItem,
    OutlineNode,
    Page,
    RevisionDetail,
    RevisionSummary,
)
from app.domain.identity.models import TenantAccess


class ErrorResponse(BaseModel):
    detail: str


class PageMeta(BaseModel):
    total: int = Field(description="Total matching items before pagination.")
    limit: int
    offset: int


class TenantResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    role: str
    permissions: list[str]

    @classmethod
    def from_access(cls, access: TenantAccess) -> TenantResponse:
        return cls(
            id=access.tenant_id,
            name=access.name,
            slug=access.slug,
            role=access.role.value,
            permissions=sorted(permission.value for permission in access.permissions),
        )


class TenantListResponse(BaseModel):
    items: list[TenantResponse]


class RevisionSummaryResponse(BaseModel):
    id: UUID
    catalog_id: UUID
    revision_number: int
    lifecycle_status: CatalogRevisionStatus
    oscal_document_uuid: UUID
    oscal_version: str
    source_version: str | None
    source_format: str | None
    created_at: datetime
    published_at: datetime | None
    control_count: int

    @classmethod
    def from_summary(cls, value: RevisionSummary) -> RevisionSummaryResponse:
        return cls(**{name: getattr(value, name) for name in cls.model_fields})


class RevisionListResponse(PageMeta):
    items: list[RevisionSummaryResponse]


class SourceDocumentResponse(BaseModel):
    title: str | None
    version: str | None
    last_modified: str | None
    published: str | None


class RevisionDetailResponse(RevisionSummaryResponse):
    group_count: int
    source_document: SourceDocumentResponse

    @classmethod
    def from_detail(cls, value: RevisionDetail) -> RevisionDetailResponse:
        summary = RevisionSummaryResponse.from_summary(value.summary)
        return cls(
            **summary.model_dump(),
            group_count=value.group_count,
            source_document=SourceDocumentResponse(
                title=value.document.title,
                version=value.document.version,
                last_modified=value.document.last_modified,
                published=value.document.published,
            ),
        )


class CatalogResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    origin_type: Literal["imported", "custom"]
    source_uri: str | None
    source_organization: str | None
    license_identifier: str | None
    revision_count: int
    latest_revision: RevisionSummaryResponse | None

    @classmethod
    def from_summary(cls, value: CatalogSummary) -> CatalogResponse:
        return cls(
            id=value.id,
            name=value.name,
            description=value.description,
            origin_type=value.origin_type,  # type: ignore[arg-type]
            source_uri=value.source_uri,
            source_organization=value.source_organization,
            license_identifier=value.license_identifier,
            revision_count=value.revision_count,
            latest_revision=(
                RevisionSummaryResponse.from_summary(value.latest_revision)
                if value.latest_revision
                else None
            ),
        )


class CatalogListResponse(PageMeta):
    items: list[CatalogResponse]


class OutlineNodeResponse(BaseModel):
    kind: Literal["group", "control"]
    id: UUID
    oscal_id: str | None
    title: str
    child_count: int

    @classmethod
    def from_node(cls, value: OutlineNode) -> OutlineNodeResponse:
        return cls(
            kind=value.kind.value,  # type: ignore[arg-type]
            id=value.id,
            oscal_id=value.oscal_id,
            title=value.title,
            child_count=value.child_count,
        )


class OutlineResponse(PageMeta):
    items: list[OutlineNodeResponse]


class ControlReference(BaseModel):
    """Stable source identity: catalog + revision + OSCAL control id."""

    catalog_id: UUID
    revision_id: UUID
    oscal_control_id: str


class GroupRefResponse(BaseModel):
    id: UUID
    oscal_group_id: str | None
    title: str


class ControlListItemResponse(BaseModel):
    id: UUID
    oscal_control_id: str
    title: str
    parent_control_id: UUID | None
    group: GroupRefResponse | None
    reference: ControlReference

    @classmethod
    def from_item(
        cls, value: ControlListItem, catalog_id: UUID, revision_id: UUID
    ) -> ControlListItemResponse:
        return cls(
            id=value.id,
            oscal_control_id=value.oscal_control_id,
            title=value.title,
            parent_control_id=value.parent_control_id,
            group=(
                GroupRefResponse(
                    id=value.group.id,
                    oscal_group_id=value.group.oscal_group_id,
                    title=value.group.title,
                )
                if value.group
                else None
            ),
            reference=ControlReference(
                catalog_id=catalog_id,
                revision_id=revision_id,
                oscal_control_id=value.oscal_control_id,
            ),
        )


class ControlListResponse(PageMeta):
    items: list[ControlListItemResponse]


class PropertyResponse(BaseModel):
    name: str
    value: str
    ns: str | None = None
    class_: str | None = Field(default=None, alias="class")
    uuid: str | None = None
    remarks: str | None = None
    model_config = ConfigDict(populate_by_name=True)


class ProfileBrowserPropertyResponse(BaseModel):
    name: str
    value: str
    ns: str | None = None


class ProfileBrowserNodeResponse(BaseModel):
    key: str
    parent_key: str | None
    kind: Literal["group", "control"]
    id: str | None
    title: str
    text: str
    properties: list[ProfileBrowserPropertyResponse]


class ProfileBrowserResponse(BaseModel):
    nodes: list[ProfileBrowserNodeResponse]


class LinkResponse(BaseModel):
    href: str
    rel: str | None = None
    text: str | None = None
    media_type: str | None = None


class PartResponse(BaseModel):
    id: str | None = None
    name: str
    ns: str | None = None
    class_: str | None = Field(default=None, alias="class")
    title: str | None = None
    prose: str | None = None
    props: list[PropertyResponse] = []
    links: list[LinkResponse] = []
    parts: list[PartResponse] = []
    model_config = ConfigDict(populate_by_name=True)


class ParameterSelectResponse(BaseModel):
    how_many: str | None = None
    choices: list[str] = []


class ParameterTestResponse(BaseModel):
    expression: str
    remarks: str | None = None


class ParameterConstraintResponse(BaseModel):
    description: str | None = None
    tests: list[ParameterTestResponse] = []


class ParameterResponse(BaseModel):
    id: str
    class_: str | None = Field(default=None, alias="class")
    label: str | None = None
    usage: str | None = None
    values: list[str] = []
    select: ParameterSelectResponse | None = None
    constraints: list[ParameterConstraintResponse] = []
    guidelines: list[str] = []
    depends_on: str | None = None
    props: list[PropertyResponse] = []
    links: list[LinkResponse] = []
    model_config = ConfigDict(populate_by_name=True)


class ResourceLinkResponse(BaseModel):
    href: str
    media_type: str | None = None


class ReferenceResponse(BaseModel):
    uuid: str
    title: str | None
    description: str | None
    citation: str | None
    rlinks: list[ResourceLinkResponse]


class AncestorResponse(BaseModel):
    kind: Literal["group", "control"]
    id: UUID
    oscal_id: str | None
    title: str


class ControlSourceCatalog(BaseModel):
    id: UUID
    name: str
    origin_type: Literal["imported", "custom"]
    source_organization: str | None
    source_uri: str | None
    license_identifier: str | None


class ControlSourceRevision(BaseModel):
    id: UUID
    revision_number: int
    lifecycle_status: CatalogRevisionStatus
    oscal_document_uuid: UUID
    oscal_version: str
    source_version: str | None


class ControlDetailResponse(BaseModel):
    id: UUID
    reference: ControlReference
    oscal_document_uuid: UUID
    oscal_version: str
    oscal_control_id: str
    title: str
    class_: str | None = Field(default=None, alias="class")
    structural_path: str
    group: GroupRefResponse | None
    parent_control_id: UUID | None
    ancestors: list[AncestorResponse]
    child_control_count: int
    parts: list[PartResponse]
    parameters: list[ParameterResponse]
    properties: list[PropertyResponse]
    links: list[LinkResponse]
    references: list[ReferenceResponse]
    raw_control: dict[str, Any]
    source_catalog: ControlSourceCatalog
    source_revision: ControlSourceRevision
    model_config = ConfigDict(populate_by_name=True)

    @classmethod
    def from_view(cls, view: ControlDetailView) -> ControlDetailResponse:
        record, content = view.record, view.content
        summary = view.revision.summary
        group = record.group
        return cls(
            id=record.id,
            reference=ControlReference(
                catalog_id=view.catalog.id,
                revision_id=summary.id,
                oscal_control_id=record.oscal_control_id,
            ),
            oscal_document_uuid=summary.oscal_document_uuid,
            oscal_version=summary.oscal_version,
            oscal_control_id=record.oscal_control_id,
            title=record.title,
            **{"class": content["class"]},
            structural_path=record.structural_path,
            group=(
                GroupRefResponse(
                    id=group.id, oscal_group_id=group.oscal_group_id, title=group.title
                )
                if group
                else None
            ),
            parent_control_id=record.parent_control_id,
            ancestors=[
                AncestorResponse(
                    kind=item.kind.value,  # type: ignore[arg-type]
                    id=item.id,
                    oscal_id=item.oscal_id,
                    title=item.title,
                )
                for item in record.ancestors
            ],
            child_control_count=record.child_control_count,
            parts=content["parts"],
            parameters=content["params"],
            properties=content["props"],
            links=content["links"],
            references=view.resources,
            raw_control=record.raw_control,
            source_catalog=ControlSourceCatalog(
                id=view.catalog.id,
                name=view.catalog.name,
                origin_type=view.catalog.origin_type,  # type: ignore[arg-type]
                source_organization=view.catalog.source_organization,
                source_uri=view.catalog.source_uri,
                license_identifier=view.catalog.license_identifier,
            ),
            source_revision=ControlSourceRevision(
                id=summary.id,
                revision_number=summary.revision_number,
                lifecycle_status=summary.lifecycle_status,
                oscal_document_uuid=summary.oscal_document_uuid,
                oscal_version=summary.oscal_version,
                source_version=summary.source_version,
            ),
        )


def page_fields(page: Page[Any]) -> dict[str, int]:
    return {"total": page.total, "limit": page.limit, "offset": page.offset}
