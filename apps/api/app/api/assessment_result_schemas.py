from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

AssessmentMethod = Literal["EXAMINE", "INTERVIEW", "TEST"]
AssessmentTargetType = Literal["statement-id", "objective-id"]


class AssessmentResultEvidenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID | None = None
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=10000)
    href: str | None = Field(default=None, max_length=2048)


class AssessmentResultObservationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID | None = None
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=10000)
    methods: list[AssessmentMethod] = Field(min_length=1, max_length=3)
    collected_at: datetime
    subject_uuids: list[UUID] = Field(default_factory=list, max_length=200)
    evidence: list[AssessmentResultEvidenceInput] = Field(default_factory=list, max_length=500)


class AssessmentResultFindingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID | None = None
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=10000)
    target_type: AssessmentTargetType
    target_id: str = Field(min_length=1, max_length=255)
    status: Literal["satisfied", "other", "not-satisfied"]
    related_observation_ids: list[UUID] = Field(default_factory=list, max_length=500)


class AssessmentResultWorkingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10000)
    reviewed_control_ids: list[str] = Field(default_factory=list, max_length=1000)
    observations: list[AssessmentResultObservationInput] = Field(
        default_factory=list, max_length=2000
    )
    findings: list[AssessmentResultFindingInput] = Field(default_factory=list, max_length=2000)
    start: datetime | None = None
    end: datetime | None = None

    @model_validator(mode="after")
    def validate_interval(self) -> AssessmentResultWorkingInput:
        if self.start is not None and self.end is not None and self.end < self.start:
            raise ValueError("Assessment Result end must be after start.")
        return self


class AssessmentResultCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assessment_plan_id: UUID
    assessment_plan_version_id: UUID
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10000)


class AssessmentResultEvidence(BaseModel):
    id: UUID
    title: str
    description: str
    href: str | None


class AssessmentResultObservation(BaseModel):
    id: UUID
    title: str
    description: str
    methods: list[AssessmentMethod]
    collected_at: datetime
    subject_uuids: list[UUID]
    evidence: list[AssessmentResultEvidence]


class AssessmentResultFinding(BaseModel):
    id: UUID
    title: str
    description: str
    target_type: AssessmentTargetType
    target_id: str
    status: str
    related_observation_ids: list[UUID]


class AssessmentResultSubjectOption(BaseModel):
    uuid: UUID
    title: str
    type: str


class AssessmentResultStatementOption(BaseModel):
    statement_id: str
    control_id: str
    title: str


class AssessmentResultObjectiveOption(BaseModel):
    objective_id: str
    control_id: str
    title: str


class AssessmentResultResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    system_id: UUID
    assessment_plan_id: UUID
    assessment_plan_version_id: UUID
    title: str
    description: str | None
    planned_control_ids: list[str]
    reviewed_control_ids: list[str]
    observations: list[AssessmentResultObservation]
    findings: list[AssessmentResultFinding]
    subject_options: list[AssessmentResultSubjectOption]
    statement_options: list[AssessmentResultStatementOption]
    objective_options: list[AssessmentResultObjectiveOption]
    start: datetime | None
    end: datetime | None
    created_at: datetime
    updated_at: datetime


class AssessmentResultValidationResponse(BaseModel):
    valid: bool
    diagnostics: list[dict]
    planned_control_ids: list[str]
    statement_options: list[AssessmentResultStatementOption]
    objective_options: list[AssessmentResultObjectiveOption]
    subject_options: list[AssessmentResultSubjectOption]
    oscal_candidate: dict[str, object] | None = None


class AssessmentResultVersionResponse(BaseModel):
    id: UUID
    assessment_result_id: UUID
    assessment_plan_version_id: UUID
    oscal_document_uuid: UUID
    oscal_version: str
    document_version: str
    last_modified: datetime
    content_sha256: str
    diagnostics: list[dict]
    created_at: datetime
    created: bool = False


