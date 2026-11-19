# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.api.dependencies import require_tenant_permission
from app.api.system_security_plan_schemas import (
    ComponentAdoptionInput,
    IncludedImplementationResponse,
    IncludeImplementationInput,
    MutationTokenResponse,
    SystemComponentInput,
    SystemComponentResponse,
    SystemComponentUpdate,
    SystemCreateInput,
    SystemInput,
    SystemResponse,
    SystemSecurityPlanInput,
    SystemSecurityPlanResponse,
    SystemSecurityPlanUpdate,
    SystemSecurityPlanValidationResponse,
    SystemSecurityPlanVersionInput,
    SystemSecurityPlanVersionResponse,
)
from app.application.implementations import StaleImplementationUpdate
from app.application.system_security_plans import (
    InvalidSystemSecurityPlan,
    StaleInformationSystemUpdate,
    StaleSystemComponentUpdate,
    StaleSystemSecurityPlanUpdate,
    SystemSecurityPlanService,
)
from app.domain.errors import EntityNotFoundError
from app.domain.identity.models import AuthorizedTenantContext, Permission
from app.persistence.database import create_session_factory

router = APIRouter(prefix="/api/v1/tenants/{tenant_id}", tags=["systems", "system-security-plans"])
ReadContext = Annotated[
    AuthorizedTenantContext, Depends(require_tenant_permission(Permission.CATALOG_READ))
]
WriteContext = Annotated[
    AuthorizedTenantContext, Depends(require_tenant_permission(Permission.CATALOG_WRITE))
]


def get_system_security_plan_service() -> SystemSecurityPlanService:
    return SystemSecurityPlanService(lambda: create_session_factory().begin())


Service = Annotated[SystemSecurityPlanService, Depends(get_system_security_plan_service)]


def _handle_not_found(error: EntityNotFoundError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(error))


def _handle_invalid(error: InvalidSystemSecurityPlan) -> HTTPException:
    return HTTPException(status_code=422, detail={"diagnostics": error.diagnostics})


def _handle_stale(error: StaleSystemSecurityPlanUpdate) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": "stale_update",
            "plan_id": str(error.plan_id),
            "expected_version": error.expected_version,
            "current_version": error.current_version,
        },
    )


def _handle_system_stale(error: StaleInformationSystemUpdate) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": "stale_update",
            "system_id": str(error.system_id),
            "expected_version": error.expected_version,
            "current_version": error.current_version,
        },
    )


def _handle_component_stale(error: StaleSystemComponentUpdate) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": "stale_update",
            "component_id": str(error.component_id),
            "expected_version": error.expected_version,
            "current_version": error.current_version,
        },
    )


def _handle_implementation_stale(error: StaleImplementationUpdate) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": "stale_update",
            "implementation_id": str(error.implementation_id),
            "expected_version": error.expected_version,
            "current_version": error.current_version,
        },
    )


@router.get("/systems", response_model=list[SystemResponse])
def list_systems(context: ReadContext, service: Service) -> list[SystemResponse]:
    return [SystemResponse.model_validate(item) for item in service.list_systems(context.tenant_id)]


@router.post("/systems", response_model=SystemResponse, status_code=201)
def create_system(
    context: WriteContext, service: Service, request: SystemCreateInput
) -> SystemResponse:
    try:
        result = service.create_system(
            context.tenant_id,
            context.membership.user_id,
            name=request.name,
            organization_id=request.organization_id,
            description=request.description,
            system_boundary=request.system_boundary,
            system_ids=[item.model_dump() for item in request.system_ids],
            information_types=[item.model_dump(mode="json") for item in request.information_types],
            operational_status=request.operational_status,
            status_remarks=request.status_remarks,
            security_sensitivity_level=request.security_sensitivity_level,
        )
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error
    except InvalidSystemSecurityPlan as error:
        raise _handle_invalid(error) from error
    return SystemResponse.model_validate(result)


@router.get("/systems/{system_id}", response_model=SystemResponse)
def get_system(context: ReadContext, service: Service, system_id: UUID) -> SystemResponse:
    try:
        return SystemResponse.model_validate(service.get_system(context.tenant_id, system_id))
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error


@router.put("/systems/{system_id}", response_model=SystemResponse)
def update_system(
    context: WriteContext,
    service: Service,
    system_id: UUID,
    request: SystemInput,
) -> SystemResponse:
    try:
        result = service.update_system(
            context.tenant_id,
            context.membership.user_id,
            system_id,
            expected_version=request.expected_version,
            name=request.name,
            description=request.description,
            system_boundary=request.system_boundary,
            system_ids=[item.model_dump() for item in request.system_ids],
            information_types=[item.model_dump(mode="json") for item in request.information_types],
            operational_status=request.operational_status,
            status_remarks=request.status_remarks,
            security_sensitivity_level=request.security_sensitivity_level,
        )
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error
    except InvalidSystemSecurityPlan as error:
        raise _handle_invalid(error) from error
    except StaleInformationSystemUpdate as error:
        raise _handle_system_stale(error) from error
    return SystemResponse.model_validate(result)


@router.get("/systems/{system_id}/components", response_model=list[SystemComponentResponse])
def list_system_components(
    context: ReadContext, service: Service, system_id: UUID
) -> list[SystemComponentResponse]:
    try:
        return [
            SystemComponentResponse.model_validate(item)
            for item in service.list_components(context.tenant_id, system_id)
        ]
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error


@router.post(
    "/systems/{system_id}/components",
    response_model=SystemComponentResponse,
    status_code=201,
)
def create_system_component(
    context: WriteContext,
    service: Service,
    system_id: UUID,
    request: SystemComponentInput,
) -> SystemComponentResponse:
    try:
        result = service.create_component(
            context.tenant_id,
            context.membership.user_id,
            system_id,
            component_type=request.component_type,
            title=request.title,
            description=request.description,
            purpose=request.purpose,
            status=request.status,
            status_remarks=request.status_remarks,
            is_system_component=request.is_system_component,
        )
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error
    except InvalidSystemSecurityPlan as error:
        raise _handle_invalid(error) from error
    return SystemComponentResponse.model_validate(result)


@router.put(
    "/systems/{system_id}/components/{component_id}",
    response_model=SystemComponentResponse,
)
def update_system_component(
    context: WriteContext,
    service: Service,
    system_id: UUID,
    component_id: UUID,
    request: SystemComponentUpdate,
) -> SystemComponentResponse:
    try:
        result = service.update_component(
            context.tenant_id,
            context.membership.user_id,
            system_id,
            component_id,
            expected_version=request.expected_version,
            title=request.title,
            description=request.description,
            purpose=request.purpose,
            status=request.status,
            status_remarks=request.status_remarks,
        )
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error
    except InvalidSystemSecurityPlan as error:
        raise _handle_invalid(error) from error
    except StaleSystemComponentUpdate as error:
        raise _handle_component_stale(error) from error
    return SystemComponentResponse.model_validate(result)


@router.post(
    "/systems/{system_id}/components/adopt",
    response_model=SystemComponentResponse,
    status_code=201,
)
def adopt_system_component(
    context: WriteContext,
    service: Service,
    system_id: UUID,
    request: ComponentAdoptionInput,
) -> SystemComponentResponse:
    try:
        result = service.adopt_component_definition(
            context.tenant_id,
            context.membership.user_id,
            system_id,
            request.source_document_id,
            request.source_component_id,
            title=request.title,
            description=request.description,
            purpose=request.purpose,
            status=request.status,
            status_remarks=request.status_remarks,
        )
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error
    except InvalidSystemSecurityPlan as error:
        raise _handle_invalid(error) from error
    return SystemComponentResponse.model_validate(result)


@router.get("/component-definition-snapshots/{snapshot_id}/components/{component_id}/export")
def export_adopted_component(
    context: ReadContext,
    service: Service,
    snapshot_id: UUID,
    component_id: UUID,
) -> dict:
    try:
        return service.export_adopted_component(context.tenant_id, snapshot_id, component_id)
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error


@router.get(
    "/systems/{system_id}/system-security-plans",
    response_model=list[SystemSecurityPlanResponse],
)
def list_system_plans(
    context: ReadContext, service: Service, system_id: UUID
) -> list[SystemSecurityPlanResponse]:
    try:
        return [
            SystemSecurityPlanResponse.model_validate(item)
            for item in service.list_plans(context.tenant_id, system_id)
        ]
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error


@router.post(
    "/systems/{system_id}/system-security-plans",
    response_model=SystemSecurityPlanResponse,
    status_code=201,
)
def create_system_plan(
    context: WriteContext,
    service: Service,
    system_id: UUID,
    request: SystemSecurityPlanInput,
) -> SystemSecurityPlanResponse:
    try:
        result = service.create_plan(
            context.tenant_id,
            context.membership.user_id,
            system_id,
            catalog_id=request.catalog_id,
            revision_id=request.revision_id,
            title=request.title,
            control_implementation_description=request.control_implementation_description,
        )
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error
    except InvalidSystemSecurityPlan as error:
        raise _handle_invalid(error) from error
    return SystemSecurityPlanResponse.model_validate(result)


@router.get("/system-security-plans/{plan_id}", response_model=SystemSecurityPlanResponse)
def get_system_plan(
    context: ReadContext, service: Service, plan_id: UUID
) -> SystemSecurityPlanResponse:
    try:
        result = service.get_plan(context.tenant_id, plan_id)
        return SystemSecurityPlanResponse.model_validate(result)
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error


@router.put("/system-security-plans/{plan_id}", response_model=SystemSecurityPlanResponse)
def update_system_plan(
    context: WriteContext,
    service: Service,
    plan_id: UUID,
    request: SystemSecurityPlanUpdate,
) -> SystemSecurityPlanResponse:
    try:
        result = service.update_plan(
            context.tenant_id,
            context.membership.user_id,
            plan_id,
            expected_version=request.expected_version,
            title=request.title,
            control_implementation_description=request.control_implementation_description,
        )
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error
    except InvalidSystemSecurityPlan as error:
        raise _handle_invalid(error) from error
    except StaleSystemSecurityPlanUpdate as error:
        raise _handle_stale(error) from error
    return SystemSecurityPlanResponse.model_validate(result)


@router.post(
    "/system-security-plans/{plan_id}/implementations/{implementation_id}",
    response_model=IncludedImplementationResponse,
    status_code=201,
)
def include_implementation(
    context: WriteContext,
    service: Service,
    plan_id: UUID,
    implementation_id: UUID,
    request: IncludeImplementationInput,
) -> IncludedImplementationResponse:
    try:
        result = service.associate_implementation(
            context.tenant_id,
            context.membership.user_id,
            plan_id,
            implementation_id,
            request.system_component_id,
            expected_version=request.expected_version,
            expected_implementation_version=request.expected_implementation_version,
        )
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error
    except InvalidSystemSecurityPlan as error:
        raise _handle_invalid(error) from error
    except StaleSystemSecurityPlanUpdate as error:
        raise _handle_stale(error) from error
    except StaleImplementationUpdate as error:
        raise _handle_implementation_stale(error) from error
    return IncludedImplementationResponse.model_validate(result)


@router.delete(
    "/system-security-plans/{plan_id}/implementations/{implementation_id}",
    response_model=MutationTokenResponse,
)
def remove_implementation(
    context: WriteContext,
    service: Service,
    plan_id: UUID,
    implementation_id: UUID,
    expected_version: int = Query(ge=1),
) -> MutationTokenResponse:
    try:
        token = service.remove_implementation(
            context.tenant_id,
            context.membership.user_id,
            plan_id,
            implementation_id,
            expected_version=expected_version,
        )
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error
    except StaleSystemSecurityPlanUpdate as error:
        raise _handle_stale(error) from error
    return MutationTokenResponse.model_validate(token)


@router.get(
    "/system-security-plans/{plan_id}/validation",
    response_model=SystemSecurityPlanValidationResponse,
)
def validate_system_plan(
    context: ReadContext, service: Service, plan_id: UUID
) -> SystemSecurityPlanValidationResponse:
    try:
        return SystemSecurityPlanValidationResponse.model_validate(
            service.validate_plan(context.tenant_id, plan_id)
        )
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error


@router.get(
    "/system-security-plans/{plan_id}/versions",
    response_model=list[SystemSecurityPlanVersionResponse],
)
def list_plan_versions(
    context: ReadContext, service: Service, plan_id: UUID
) -> list[SystemSecurityPlanVersionResponse]:
    try:
        return [
            SystemSecurityPlanVersionResponse.model_validate(item)
            for item in service.list_versions(context.tenant_id, plan_id)
        ]
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error


@router.post(
    "/system-security-plans/{plan_id}/versions",
    response_model=SystemSecurityPlanVersionResponse,
    status_code=201,
)
def create_plan_version(
    context: WriteContext,
    service: Service,
    plan_id: UUID,
    request: SystemSecurityPlanVersionInput,
    response: Response,
) -> SystemSecurityPlanVersionResponse:
    try:
        result = service.create_version(
            context.tenant_id,
            context.membership.user_id,
            plan_id,
            expected_version=request.expected_version,
        )
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error
    except InvalidSystemSecurityPlan as error:
        raise _handle_invalid(error) from error
    except StaleSystemSecurityPlanUpdate as error:
        raise _handle_stale(error) from error
    if not result["created"]:
        response.status_code = 200
    return SystemSecurityPlanVersionResponse.model_validate(result)


@router.get(
    "/system-security-plans/{plan_id}/versions/{version_id}",
    response_model=SystemSecurityPlanVersionResponse,
)
def get_plan_version(
    context: ReadContext, service: Service, plan_id: UUID, version_id: UUID
) -> SystemSecurityPlanVersionResponse:
    try:
        versions = service.list_versions(context.tenant_id, plan_id)
        version = next((item for item in versions if item["id"] == version_id), None)
        if version is None:
            raise EntityNotFoundError("SSP version not found.")
        return SystemSecurityPlanVersionResponse.model_validate(version)
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error


@router.get("/system-security-plans/{plan_id}/versions/{version_id}/export")
def export_plan_version(
    context: ReadContext, service: Service, plan_id: UUID, version_id: UUID
) -> dict:
    try:
        return service.export_version(context.tenant_id, plan_id, version_id)
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error
