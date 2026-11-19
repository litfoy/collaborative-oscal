# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.application.component_definitions import ComponentInput, ComponentRequirementInput
from app.domain.component_definitions import ComponentDefinition


class ComponentRequirementInputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    catalog_id: UUID
    revision_id: UUID
    control_id: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=50000)

    @model_validator(mode="after")
    def normalize_description(self) -> ComponentRequirementInputModel:
        self.description = self.description.strip()
        if not self.description:
            raise ValueError("Describe how the component addresses this requirement.")
        return self

    def to_domain(self) -> ComponentRequirementInput:
        return ComponentRequirementInput(
            self.catalog_id, self.revision_id, self.control_id, self.description
        )


class ComponentInputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID | None = None
    type: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(max_length=50000)
    requirements: list[ComponentRequirementInputModel] = Field(
        default_factory=list, max_length=1000
    )

    @model_validator(mode="after")
    def normalize_fields(self) -> ComponentInputModel:
        self.type = self.type.strip()
        self.title = self.title.strip()
        if not self.type or not self.title:
            raise ValueError("Component type and title must not be empty.")
        keys = [
            (item.catalog_id, item.revision_id, item.control_id)
            for item in self.requirements
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("A requirement may be associated only once per component.")
        return self

    def to_domain(self) -> ComponentInput:
        return ComponentInput(
            self.id,
            self.type,
            self.title,
            self.description,
            [item.to_domain() for item in self.requirements],
        )


class ComponentDefinitionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=255)
    type: str = Field(min_length=1, max_length=128)
    description: str = Field(max_length=50000)
    requirements: list[ComponentRequirementInputModel] = Field(
        default_factory=list, max_length=1000
    )

    @model_validator(mode="after")
    def normalize_fields(self) -> ComponentDefinitionCreateRequest:
        self.title = self.title.strip()
        self.type = self.type.strip()
        if not self.title or not self.type:
            raise ValueError("Component type and title must not be empty.")
        keys = [
            (item.catalog_id, item.revision_id, item.control_id)
            for item in self.requirements
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("A requirement may be associated only once per component.")
        return self


class ComponentDefinitionUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=255)
    components: list[ComponentInputModel] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def normalize_title(self) -> ComponentDefinitionUpdateRequest:
        self.title = self.title.strip()
        if not self.title:
            raise ValueError("Document title must not be empty.")
        ids = [item.id for item in self.components if item.id is not None]
        if len(ids) != len(set(ids)):
            raise ValueError("Component identities must be unique.")
        return self


class ComponentRequirementResponse(BaseModel):
    catalog_id: UUID
    revision_id: UUID
    control_id: str
    description: str


class ComponentResponse(BaseModel):
    id: UUID
    oscal_uuid: UUID
    type: str
    title: str
    description: str
    requirements: list[ComponentRequirementResponse]


class ComponentDefinitionResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    title: str
    oscal_document_uuid: UUID
    oscal_version: str
    version: str
    components: list[ComponentResponse]
    created_by: UUID
    updated_by: UUID
    created_at: datetime
    updated_at: datetime
    concurrency_version: int

    @classmethod
    def from_definition(cls, definition: ComponentDefinition) -> ComponentDefinitionResponse:
        return cls(
            id=definition.id,
            tenant_id=definition.tenant_id,
            title=definition.title,
            oscal_document_uuid=definition.oscal_document_uuid,
            oscal_version=definition.oscal_version,
            version=definition.version,
            components=[
                ComponentResponse(
                    id=component.id,
                    oscal_uuid=component.oscal_uuid,
                    type=component.type,
                    title=component.title,
                    description=component.description,
                    requirements=[
                        ComponentRequirementResponse(
                            catalog_id=requirement.catalog_id,
                            revision_id=requirement.revision_id,
                            control_id=requirement.control_id,
                            description=requirement.description,
                        )
                        for requirement in component.requirements
                    ],
                )
                for component in definition.components
            ],
            created_by=definition.created_by,
            updated_by=definition.updated_by,
            created_at=definition.created_at,
            updated_at=definition.updated_at,
            concurrency_version=definition.concurrency_version,
        )


class ComponentDefinitionPage(BaseModel):
    items: list[ComponentDefinitionResponse]
    total: int
    limit: int
    offset: int


class ComponentDefinitionValidationErrorResponse(BaseModel):
    detail: str | list[dict[str, Any]]
