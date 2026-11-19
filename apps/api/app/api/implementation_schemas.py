# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.implementations import (
    ImplementationStatus,
    OscalImplementationStatus,
    ResponsibilityKind,
)


class ResponsibilityInput(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    kind: ResponsibilityKind
    user_id: UUID | None = None
    role: str = Field(default="", max_length=255)

    @model_validator(mode="after")
    def validate_party(self) -> "ResponsibilityInput":
        self.role = self.role.strip()
        if self.user_id is None and not self.role:
            raise ValueError("A responsibility requires a person or role.")
        return self


class ImplementationInformation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(max_length=50000)
    status: ImplementationStatus
    evidence_references: list[str] = Field(max_length=100)
    responsibilities: list[ResponsibilityInput] = Field(max_length=100)
    oscal_implementation_status: OscalImplementationStatus | None = None
    oscal_status_explanation: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def validate_lists(self) -> "ImplementationInformation":
        if any(not item.strip() or len(item) > 2048 for item in self.evidence_references):
            raise ValueError("Evidence references must be nonempty and at most 2048 characters.")
        keys = [(item.kind, item.user_id, item.role) for item in self.responsibilities]
        if len(keys) != len(set(keys)):
            raise ValueError("Responsibilities must be unique.")
        if self.oscal_implementation_status in {
            OscalImplementationStatus.PLANNED,
            OscalImplementationStatus.ALTERNATIVE,
            OscalImplementationStatus.NOT_APPLICABLE,
        } and not (self.oscal_status_explanation or "").strip():
            raise ValueError(
                "Planned, alternative, and not-applicable states require an explanation."
            )
        return self


class ImplementationCreate(ImplementationInformation):
    description: str = Field(default="", max_length=50000)
    status: ImplementationStatus = ImplementationStatus.NOT_STARTED
    evidence_references: list[str] = Field(default_factory=list, max_length=100)
    responsibilities: list[ResponsibilityInput] = Field(default_factory=list, max_length=100)
    organization_id: UUID | None = None
    profile_id: UUID | None = None
    profile_import_id: UUID | None = None
    catalog_id: UUID
    revision_id: UUID
    oscal_control_id: str = Field(min_length=1, max_length=255)


class ImplementationResponse(ImplementationInformation):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    organization_id: UUID | None
    system_id: UUID | None = None
    system_component_id: UUID | None = None
    profile_id: UUID | None
    profile_import_id: UUID | None
    catalog_id: UUID
    revision_id: UUID
    oscal_control_id: str
    created_by: UUID
    updated_by: UUID
    created_at: datetime
    updated_at: datetime
    concurrency_version: int


class ImplementationUpdate(ImplementationInformation):
    expected_version: int = Field(ge=1)


class ImplementationPage(BaseModel):
    items: list[ImplementationResponse]
    total: int
    limit: int
    offset: int


class OrganizationOption(BaseModel):
    id: UUID
    name: str


class PersonOption(BaseModel):
    id: UUID
    display_name: str | None


class ImplementationOptions(BaseModel):
    organizations: list[OrganizationOption]
    people: list[PersonOption]
