from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class CatalogOriginType(StrEnum):
    IMPORTED = "imported"
    CUSTOM = "custom"


class CatalogRevisionStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"


JsonObject = dict[str, Any]


@dataclass(frozen=True, slots=True)
class Catalog:
    id: UUID
    tenant_id: UUID
    name: str
    description: str | None
    origin_type: CatalogOriginType
    source_uri: str | None
    source_organization: str | None
    license_identifier: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CatalogRevision:
    id: UUID
    tenant_id: UUID
    catalog_id: UUID
    revision_number: int
    lifecycle_status: CatalogRevisionStatus
    oscal_document_uuid: UUID
    oscal_version: str
    source_version: str | None
    content_sha256: str
    content: JsonObject
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None


@dataclass(frozen=True, slots=True)
class CatalogGroupIndex:
    id: UUID
    tenant_id: UUID
    catalog_revision_id: UUID
    oscal_group_id: str | None
    parent_group_id: UUID | None
    structural_path: str
    title: str
    display_order: int


@dataclass(frozen=True, slots=True)
class CatalogControlIndex:
    id: UUID
    tenant_id: UUID
    catalog_revision_id: UUID
    oscal_control_id: str
    parent_control_id: UUID | None
    group_id: UUID | None
    title: str
    structural_path: str
    display_order: int
