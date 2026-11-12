from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from collaborative_oscal_oscal.profile import selected_control_ids
from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.profiles.models import Profile

ControlId = Annotated[str, Field(min_length=1, max_length=255)]


class ProfileImportInput(BaseModel):
    id: UUID | None = None
    catalog_id: UUID
    revision_id: UUID
    control_ids: list[ControlId] = Field(min_length=1, max_length=10000)

    @field_validator("control_ids")
    @classmethod
    def unique_ids(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("Control IDs must be unique.")
        return values


class ProfileCreateRequest(BaseModel):
    catalog_id: UUID | None = None
    revision_id: UUID | None = None
    imports: list[ProfileImportInput] | None = Field(default=None, min_length=1, max_length=100)
    oscal_version: str | None = None
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=10000)
    control_ids: list[ControlId] | None = Field(default=None, min_length=1, max_length=10000)

    @model_validator(mode="after")
    def validate_sources(self) -> ProfileCreateRequest:
        if self.imports is not None:
            if (
                self.catalog_id is not None
                or self.revision_id is not None
                or self.control_ids is not None
            ):
                raise ValueError("Use imports or the legacy source fields, not both.")
            if sum(len(item.control_ids) for item in self.imports) > 10000:
                raise ValueError("A profile supports at most 10000 control selections.")
        elif self.catalog_id is None or self.revision_id is None or self.control_ids is None:
            raise ValueError("A source and control selections are required.")
        return self

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        title = value.strip()
        if not title:
            raise ValueError("Title must not be empty.")
        return title

    @field_validator("control_ids")
    @classmethod
    def require_unique_control_ids(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        if len(values) != len(set(values)):
            raise ValueError("Control IDs must be unique.")
        return values


class ProfileUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10000)
    control_ids: list[ControlId] | None = Field(default=None, min_length=1, max_length=10000)
    imports: list[ProfileImportInput] | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_sources(self) -> ProfileUpdateRequest:
        if (self.control_ids is None) == (self.imports is None):
            raise ValueError("Provide either imports or control_ids.")
        if self.imports and sum(len(item.control_ids) for item in self.imports) > 10000:
            raise ValueError("A profile supports at most 10000 control selections.")
        return self

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        title = value.strip()
        if not title:
            raise ValueError("Title must not be empty.")
        return title

    @field_validator("control_ids")
    @classmethod
    def require_unique_control_ids(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        if len(values) != len(set(values)):
            raise ValueError("Control IDs must be unique.")
        return values


class ProfileResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    catalog_id: UUID
    revision_id: UUID
    title: str
    description: str
    oscal_version: str
    control_ids: list[str]
    imports: list[ProfileImportInput]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_profile(cls, profile: Profile) -> ProfileResponse:
        return cls(
            id=profile.id,
            tenant_id=profile.tenant_id,
            catalog_id=profile.imports[0].catalog_id,
            revision_id=profile.imports[0].revision_id,
            title=profile.title,
            description=profile.document["profile"]["metadata"].get("remarks", ""),
            oscal_version=profile.document["profile"]["metadata"]["oscal-version"],
            control_ids=selected_control_ids(profile.document),
            imports=[
                ProfileImportInput(
                    id=item.id,
                    catalog_id=item.catalog_id,
                    revision_id=item.revision_id,
                    control_ids=item.control_ids,
                )
                for item in profile.imports
            ],
            created_at=profile.created_at,
            updated_at=profile.updated_at,
        )


class ProfileListResponse(BaseModel):
    items: list[ProfileResponse]
    total: int
    limit: int
    offset: int


class ProfileValidationErrorResponse(BaseModel):
    detail: str | list[dict[str, Any]]
