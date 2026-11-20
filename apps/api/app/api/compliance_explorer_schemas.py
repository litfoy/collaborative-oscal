# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

from uuid import UUID

from pydantic import BaseModel

from app.domain.implementations import ImplementationStatus, OscalImplementationStatus


class ComplianceExplorerSystemResponse(BaseModel):
    id: UUID
    name: str


class ComplianceExplorerProfileResponse(BaseModel):
    id: UUID
    title: str


class ComplianceExplorerControlReferenceResponse(BaseModel):
    catalog_id: UUID
    revision_id: UUID
    oscal_control_id: str


class ComplianceExplorerControlMembershipResponse(BaseModel):
    profile_id: UUID
    profile_title: str
    profile_import_id: UUID


class ComplianceExplorerSystemComponentResponse(BaseModel):
    id: UUID
    title: str | None


class ComplianceExplorerImplementationResponse(BaseModel):
    id: UUID
    status: ImplementationStatus
    oscal_implementation_status: OscalImplementationStatus | None = None
    oscal_status_explanation: str | None = None
    profile_id: UUID | None = None
    profile_import_id: UUID | None = None
    system_component_id: UUID | None = None
    system_component: ComplianceExplorerSystemComponentResponse | None = None


class ComplianceExplorerControlResponse(BaseModel):
    reference: ComplianceExplorerControlReferenceResponse
    title: str
    memberships: list[ComplianceExplorerControlMembershipResponse]
    implementations: list[ComplianceExplorerImplementationResponse]


class ComplianceExplorerPageResponse(BaseModel):
    system: ComplianceExplorerSystemResponse
    profiles: list[ComplianceExplorerProfileResponse]
    items: list[ComplianceExplorerControlResponse]
    total: int
    limit: int
    offset: int

