from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Organization:
    id: UUID
    tenant_id: UUID
    parent_organization_id: UUID | None
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime
