from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ProfileImport:
    id: UUID
    catalog_id: UUID
    revision_id: UUID
    control_ids: list[str]


@dataclass(frozen=True, slots=True)
class Profile:
    id: UUID
    tenant_id: UUID
    imports: list[ProfileImport]
    title: str
    document: dict[str, Any]
    created_at: datetime
    updated_at: datetime
