# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SystemIdentifierInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=255)
    identifier_type: str | None = Field(default=None, min_length=1, max_length=255)


class InformationTypeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uuid: UUID | None = None
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=5000)


class SystemFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=50000)
    system_boundary: str | None = Field(default=None, max_length=50000)
    system_ids: list[SystemIdentifierInput] = Field(default_factory=list, max_length=100)
    information_types: list[InformationTypeInput] = Field(default_factory=list, max_length=100)
    operational_status: str | None = None
    status_remarks: str | None = Field(default=None, max_length=5000)
    security_sensitivity_level: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def validate_other_status(self) -> "SystemInput":
        if self.operational_status == "other" and not (self.status_remarks or "").strip():
            raise ValueError("An explanation is required for the 'other' status.")
        return self


class SystemCreateInput(SystemFields):
    organization_id: UUID | None = None


class SystemInput(SystemFields):
    expected_version: int = Field(ge=1)


class SystemResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    organization_id: UUID | None
    name: str
    description: str | None
    system_boundary: str | None
    system_ids: list[dict]
    information_types: list[dict]
    operational_status: str | None
    status_remarks: str | None
    security_sensitivity_level: str | None
    created_at: datetime
    updated_at: datetime
    concurrency_version: int


class SystemComponentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    component_type: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=50000)
    purpose: str | None = Field(default=None, max_length=50000)
    status: str
    status_remarks: str | None = Field(default=None, max_length=5000)
    is_system_component: bool = False


class SystemComponentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=50000)
    purpose: str | None = Field(default=None, max_length=50000)
    status: str
    status_remarks: str | None = Field(default=None, max_length=5000)


class ComponentAdoptionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_document_id: UUID
    source_component_id: UUID
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=50000)
    purpose: str | None = Field(default=None, max_length=50000)
    status: str
    status_remarks: str | None = Field(default=None, max_length=5000)


class SystemComponentResponse(BaseModel):
    id: UUID
    system_id: UUID
    oscal_component_uuid: UUID
    component: dict
    is_system_component: bool
    source_snapshot_id: UUID | None
    source_component_uuid: UUID | None
    concurrency_version: int


class SystemSecurityPlanInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    catalog_id: UUID
    revision_id: UUID
    title: str = Field(min_length=1, max_length=255)
    control_implementation_description: str | None = Field(default=None, max_length=50000)


class SystemSecurityPlanUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=255)
    control_implementation_description: str | None = Field(default=None, max_length=50000)


class IncludedImplementation(BaseModel):
    implementation_id: UUID
    oscal_control_id: str
    system_component_id: UUID


class SystemSecurityPlanResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    system_id: UUID
    catalog_id: UUID
    revision_id: UUID
    catalog_name: str
    title: str
    control_implementation_description: str | None
    included_implementations: list[IncludedImplementation]
    baseline_control_count: int
    documented_control_count: int
    created_at: datetime
    updated_at: datetime
    concurrency_version: int


class IncludeImplementationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    expected_implementation_version: int = Field(ge=1)
    system_component_id: UUID


class SystemSecurityPlanVersionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)


class Diagnostic(BaseModel):
    severity: str
    code: str
    message: str


class SystemSecurityPlanValidationResponse(BaseModel):
    valid: bool
    diagnostics: list[Diagnostic]
    baseline_control_count: int
    documented_control_count: int


class SystemSecurityPlanVersionResponse(BaseModel):
    id: UUID
    system_security_plan_id: UUID
    catalog_id: UUID
    revision_id: UUID
    oscal_document_uuid: UUID
    oscal_version: str
    document_version: str
    last_modified: datetime
    content_sha256: str
    diagnostics: list[Diagnostic]
    created_at: datetime
    created: bool = False
    concurrency_version: int | None = None


class IncludedImplementationResponse(BaseModel):
    implementation_id: UUID
    system_component_id: UUID
    oscal_control_id: str
    concurrency_version: int
    implementation_concurrency_version: int


class MutationTokenResponse(BaseModel):
    concurrency_version: int
