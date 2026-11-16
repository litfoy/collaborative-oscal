from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

AssessmentMethod = Literal["EXAMINE", "INTERVIEW", "TEST"]


class AssessmentSourceObjectiveInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective_id: str = Field(min_length=1, max_length=255)
    control_id: str = Field(min_length=1, max_length=255)


class AssessmentLocalObjectiveInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective_id: str = Field(min_length=1, max_length=255)
    control_id: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=10000)
    methods: list[AssessmentMethod] = Field(default_factory=list, max_length=3)


class AssessmentActivityStepInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID | None = None
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=10000)


class AssessmentActivityInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID | None = None
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=10000)
    methods: list[AssessmentMethod] = Field(min_length=1, max_length=3)
    steps: list[AssessmentActivityStepInput] = Field(default_factory=list, max_length=200)
    control_ids: list[str] = Field(default_factory=list, max_length=500)
    objective_ids: list[str] = Field(default_factory=list, max_length=500)
    planned_evidence: str | None = Field(default=None, max_length=10000)


class AssessmentTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID | None = None
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10000)
    activity_ids: list[UUID] = Field(default_factory=list, max_length=200)
    subject_uuids: list[UUID] = Field(default_factory=list, max_length=200)
    role_ids: list[str] = Field(default_factory=list, max_length=100)
    on_date: datetime | None = None
    start: datetime | None = None
    end: datetime | None = None

    @model_validator(mode="after")
    def validate_timing(self) -> AssessmentTaskInput:
        if self.on_date is not None and (self.start is not None or self.end is not None):
            raise ValueError("Specify either on_date or a start/end range, not both.")
        if (self.start is None) != (self.end is None):
            raise ValueError("Both start and end are required when using a date range.")
        if self.start is not None and self.end is not None and self.end < self.start:
            raise ValueError("Task end must be after task start.")
        return self


class AssessmentRoleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_id: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10000)
    party_uuids: list[UUID] = Field(default_factory=list, max_length=100)


class AssessmentPartyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uuid: UUID | None = None
    party_type: Literal["person", "organization"]
    name: str = Field(min_length=1, max_length=255)


class AssessmentPlanWorkingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10000)
    control_ids: list[str] = Field(default_factory=list, max_length=1000)
    source_objectives: list[AssessmentSourceObjectiveInput] = Field(
        default_factory=list, max_length=1000
    )
    local_objectives: list[AssessmentLocalObjectiveInput] = Field(
        default_factory=list, max_length=1000
    )
    subject_uuids: list[UUID] = Field(default_factory=list, max_length=1000)
    activities: list[AssessmentActivityInput] = Field(default_factory=list, max_length=1000)
    tasks: list[AssessmentTaskInput] = Field(default_factory=list, max_length=1000)
    roles: list[AssessmentRoleInput] = Field(default_factory=list, max_length=200)
    parties: list[AssessmentPartyInput] = Field(default_factory=list, max_length=200)
    terms: str | None = Field(default=None, max_length=20000)


class AssessmentPlanCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ssp_version_id: UUID
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10000)


class AssessmentSourceObjective(BaseModel):
    objective_id: str
    control_id: str


class AssessmentLocalObjective(BaseModel):
    objective_id: str
    control_id: str
    description: str
    methods: list[AssessmentMethod]


class AssessmentActivityStep(BaseModel):
    id: UUID
    title: str
    description: str


class AssessmentActivity(BaseModel):
    id: UUID
    title: str
    description: str
    methods: list[AssessmentMethod]
    steps: list[AssessmentActivityStep]
    control_ids: list[str]
    objective_ids: list[str]
    planned_evidence: str | None


class AssessmentTask(BaseModel):
    id: UUID
    title: str
    description: str | None
    activity_ids: list[UUID]
    subject_uuids: list[UUID]
    role_ids: list[str]
    on_date: datetime | None
    start: datetime | None
    end: datetime | None


class AssessmentRole(BaseModel):
    role_id: str
    title: str
    description: str | None
    party_uuids: list[UUID]


class AssessmentParty(BaseModel):
    uuid: UUID
    party_type: Literal["person", "organization"]
    name: str


class AssessmentPlanResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    system_id: UUID
    system_security_plan_id: UUID
    system_security_plan_version_id: UUID
    title: str
    description: str | None
    control_ids: list[str]
    source_objectives: list[AssessmentSourceObjective]
    local_objectives: list[AssessmentLocalObjective]
    subject_uuids: list[UUID]
    activities: list[AssessmentActivity]
    tasks: list[AssessmentTask]
    roles: list[AssessmentRole]
    parties: list[AssessmentParty]
    terms: str | None
    baseline_catalog_id: UUID
    baseline_revision_id: UUID
    ssp_oscal_version: str
    created_at: datetime
    updated_at: datetime


class AssessmentSourceObjectiveCatalogItem(BaseModel):
    objective_id: str
    control_id: str
    title: str
    description: str | None


class AssessmentPlanValidationResponse(BaseModel):
    valid: bool
    diagnostics: list[dict]
    source_objectives: list[AssessmentSourceObjectiveCatalogItem]
    oscal_candidate: dict[str, object] | None = None


class AssessmentPlanVersionResponse(BaseModel):
    id: UUID
    assessment_plan_id: UUID
    system_security_plan_version_id: UUID
    oscal_document_uuid: UUID
    oscal_version: str
    document_version: str
    last_modified: datetime
    content_sha256: str
    diagnostics: list[dict]
    created_at: datetime
    created: bool = False



