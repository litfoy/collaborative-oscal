from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.domain.profiles.models import Profile

ControlId = Annotated[str, Field(min_length=1, max_length=255)]


class ProfileCreateRequest(BaseModel):
    catalog_id: UUID
    revision_id: UUID
    title: str = Field(min_length=1, max_length=255)
    control_ids: list[ControlId] = Field(min_length=1, max_length=1000)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        title = value.strip()
        if not title:
            raise ValueError("Title must not be empty.")
        return title

    @field_validator("control_ids")
    @classmethod
    def require_unique_control_ids(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("Control IDs must be unique.")
        return values


class ProfileUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    control_ids: list[ControlId] = Field(min_length=1, max_length=1000)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        title = value.strip()
        if not title:
            raise ValueError("Title must not be empty.")
        return title

    @field_validator("control_ids")
    @classmethod
    def require_unique_control_ids(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("Control IDs must be unique.")
        return values


class ProfileResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    catalog_id: UUID
    revision_id: UUID
    title: str
    control_ids: list[str]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_profile(cls, profile: Profile) -> ProfileResponse:
        return cls(
            id=profile.id,
            tenant_id=profile.tenant_id,
            catalog_id=profile.catalog_id,
            revision_id=profile.revision_id,
            title=profile.title,
            control_ids=profile.document["profile"]["imports"][0]["include-controls"][0][
                "with-ids"
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
