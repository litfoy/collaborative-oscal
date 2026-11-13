from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class MappingEntrySpec:
    id: UUID | None
    sources: tuple[str, ...]
    targets: tuple[str, ...]
    relationship: str
    matching_rationale: str
    justification: str


@dataclass(frozen=True, slots=True)
class MappingPairSpec:
    id: UUID | None
    source_catalog_id: UUID
    source_revision_id: UUID
    target_catalog_id: UUID
    target_revision_id: UUID
    entries: tuple[MappingEntrySpec, ...]


@dataclass(frozen=True, slots=True)
class MappingCollection:
    id: UUID
    tenant_id: UUID
    document: dict[str, Any]
    created_by: UUID
    updated_by: UUID
    created_at: datetime
    updated_at: datetime
