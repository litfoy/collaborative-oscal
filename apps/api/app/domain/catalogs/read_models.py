"""Read models for browsing catalogs. They intentionally exclude full OSCAL documents."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from app.domain.catalogs.models import CatalogRevisionStatus


class OutlineNodeKind(StrEnum):
    GROUP = "group"
    CONTROL = "control"


@dataclass(frozen=True, slots=True)
class RevisionSummary:
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


@dataclass(frozen=True, slots=True)
class RevisionDocumentMetadata:
    title: str | None
    version: str | None
    last_modified: str | None
    published: str | None


@dataclass(frozen=True, slots=True)
class RevisionDetail:
    summary: RevisionSummary
    group_count: int
    document: RevisionDocumentMetadata


@dataclass(frozen=True, slots=True)
class CatalogSummary:
    id: UUID
    name: str
    description: str | None
    origin_type: str
    source_uri: str | None
    source_organization: str | None
    license_identifier: str | None
    revision_count: int
    latest_revision: RevisionSummary | None


@dataclass(frozen=True, slots=True)
class OutlineNode:
    kind: OutlineNodeKind
    id: UUID
    oscal_id: str | None
    title: str
    child_count: int


@dataclass(frozen=True, slots=True)
class GroupRef:
    id: UUID
    oscal_group_id: str | None
    title: str


@dataclass(frozen=True, slots=True)
class ControlListItem:
    id: UUID
    oscal_control_id: str
    title: str
    parent_control_id: UUID | None
    group: GroupRef | None


@dataclass(frozen=True, slots=True)
class AncestorRef:
    kind: OutlineNodeKind
    id: UUID
    oscal_id: str | None
    title: str


@dataclass(frozen=True, slots=True)
class ControlRecordView:
    """Indexed control plus the raw OSCAL control object extracted from the revision."""

    id: UUID
    oscal_control_id: str
    title: str
    structural_path: str
    parent_control_id: UUID | None
    group: GroupRef | None
    ancestors: list[AncestorRef]
    child_control_count: int
    raw_control: dict[str, Any]
    resources: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class Page[T]:
    items: list[T]
    total: int
    limit: int
    offset: int
