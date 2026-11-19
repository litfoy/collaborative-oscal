# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class ImplementationStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    IMPLEMENTED = "implemented"
    NOT_APPLICABLE = "not_applicable"


class ResponsibilityKind(StrEnum):
    ACCOUNTABLE = "accountable"
    RESPONSIBLE = "responsible"
    PARTICIPANT = "participant"


class OscalImplementationStatus(StrEnum):
    IMPLEMENTED = "implemented"
    PARTIAL = "partial"
    PLANNED = "planned"
    ALTERNATIVE = "alternative"
    NOT_APPLICABLE = "not-applicable"


@dataclass(frozen=True, slots=True)
class Responsibility:
    kind: ResponsibilityKind
    user_id: UUID | None
    role: str


@dataclass(frozen=True, slots=True)
class ImplementationInformation:
    description: str
    status: ImplementationStatus
    evidence_references: list[str]
    responsibilities: list[Responsibility]
    oscal_implementation_status: OscalImplementationStatus | None = None
    oscal_status_explanation: str | None = None


@dataclass(frozen=True, slots=True)
class ControlImplementation:
    id: UUID
    tenant_id: UUID
    organization_id: UUID | None
    profile_id: UUID | None
    profile_import_id: UUID | None
    catalog_id: UUID
    revision_id: UUID
    oscal_control_id: str
    description: str
    status: ImplementationStatus
    evidence_references: list[str]
    responsibilities: list[Responsibility]
    created_by: UUID
    updated_by: UUID
    created_at: datetime
    updated_at: datetime
    concurrency_version: int
    system_id: UUID | None = None
    system_component_id: UUID | None = None
    oscal_implementation_status: OscalImplementationStatus | None = None
    oscal_status_explanation: str | None = None
