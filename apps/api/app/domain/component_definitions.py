# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ComponentRequirement:
    catalog_id: UUID
    revision_id: UUID
    control_id: str
    description: str


@dataclass(frozen=True, slots=True)
class ReusableComponent:
    id: UUID
    oscal_uuid: UUID
    type: str
    title: str
    description: str
    requirements: list[ComponentRequirement]


@dataclass(frozen=True, slots=True)
class ComponentDefinition:
    id: UUID
    tenant_id: UUID
    title: str
    oscal_document_uuid: UUID
    oscal_version: str
    version: str
    components: list[ReusableComponent]
    created_by: UUID
    updated_by: UUID
    created_at: datetime
    updated_at: datetime
    concurrency_version: int
