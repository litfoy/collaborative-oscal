from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response

from app.api.assessment_result_schemas import (
    AssessmentResultCreateInput,
    AssessmentResultResponse,
    AssessmentResultValidationResponse,
    AssessmentResultVersionResponse,
    AssessmentResultWorkingInput,
)
from app.api.dependencies import require_tenant_permission
from app.application.assessment_results import (
    AssessmentResultService,
    InvalidAssessmentResult,
)
from app.domain.errors import EntityNotFoundError
from app.domain.identity.models import AuthorizedTenantContext, Permission
from app.persistence.database import create_session_factory

router = APIRouter(prefix="/api/v1/tenants/{tenant_id}", tags=["assessment-results"])
ReadContext = Annotated[
    AuthorizedTenantContext, Depends(require_tenant_permission(Permission.CATALOG_READ))
]
WriteContext = Annotated[
    AuthorizedTenantContext, Depends(require_tenant_permission(Permission.CATALOG_WRITE))
]


def get_assessment_result_service() -> AssessmentResultService:
    return AssessmentResultService(lambda: create_session_factory().begin())


Service = Annotated[AssessmentResultService, Depends(get_assessment_result_service)]


def _handle_not_found(error: EntityNotFoundError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(error))


def _handle_invalid(error: InvalidAssessmentResult) -> HTTPException:
    return HTTPException(status_code=422, detail={"diagnostics": error.diagnostics})


@router.get(
    "/systems/{system_id}/assessment-results", response_model=list[AssessmentResultResponse]
)
def list_assessment_results(
    context: ReadContext, service: Service, system_id: UUID
) -> list[AssessmentResultResponse]:
    try:
        return [
            AssessmentResultResponse.model_validate(item)
            for item in service.list_results(context.tenant_id, system_id)
        ]
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error


@router.post(
    "/systems/{system_id}/assessment-results",
    response_model=AssessmentResultResponse,
    status_code=201,
)
def create_assessment_result(
    context: WriteContext,
    service: Service,
    system_id: UUID,
    request: AssessmentResultCreateInput,
) -> AssessmentResultResponse:
    try:
        created = service.create_result(
            context.tenant_id,
            context.membership.user_id,
            system_id,
            assessment_plan_id=request.assessment_plan_id,
            assessment_plan_version_id=request.assessment_plan_version_id,
            title=request.title,
            description=request.description,
        )
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error
    except InvalidAssessmentResult as error:
        raise _handle_invalid(error) from error
    return AssessmentResultResponse.model_validate(created)


@router.get("/assessment-results/{result_id}", response_model=AssessmentResultResponse)
def get_assessment_result(
    context: ReadContext, service: Service, result_id: UUID
) -> AssessmentResultResponse:
    try:
        result = service.get_result(context.tenant_id, result_id)
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error
    return AssessmentResultResponse.model_validate(result)


@router.put("/assessment-results/{result_id}", response_model=AssessmentResultResponse)
def update_assessment_result(
    context: WriteContext,
    service: Service,
    result_id: UUID,
    request: AssessmentResultWorkingInput,
) -> AssessmentResultResponse:
    try:
        result = service.update_result(
            context.tenant_id,
            context.membership.user_id,
            result_id,
            title=request.title,
            description=request.description,
            working_data=request.model_dump(mode="json", exclude={"title", "description"}),
        )
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error
    except InvalidAssessmentResult as error:
        raise _handle_invalid(error) from error
    return AssessmentResultResponse.model_validate(result)


@router.get(
    "/assessment-results/{result_id}/validation",
    response_model=AssessmentResultValidationResponse,
)
def validate_assessment_result(
    context: ReadContext, service: Service, result_id: UUID
) -> AssessmentResultValidationResponse:
    try:
        return AssessmentResultValidationResponse.model_validate(
            service.validate_result(context.tenant_id, result_id)
        )
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error


@router.get(
    "/assessment-results/{result_id}/versions",
    response_model=list[AssessmentResultVersionResponse],
)
def list_assessment_result_versions(
    context: ReadContext, service: Service, result_id: UUID
) -> list[AssessmentResultVersionResponse]:
    try:
        return [
            AssessmentResultVersionResponse.model_validate(item)
            for item in service.list_versions(context.tenant_id, result_id)
        ]
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error


@router.post(
    "/assessment-results/{result_id}/versions",
    response_model=AssessmentResultVersionResponse,
    status_code=201,
)
def create_assessment_result_version(
    context: WriteContext, service: Service, result_id: UUID, response: Response
) -> AssessmentResultVersionResponse:
    try:
        result = service.create_version(
            context.tenant_id,
            context.membership.user_id,
            result_id,
        )
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error
    except InvalidAssessmentResult as error:
        raise _handle_invalid(error) from error
    if not result["created"]:
        response.status_code = 200
    return AssessmentResultVersionResponse.model_validate(result)


@router.get(
    "/assessment-results/{result_id}/versions/{version_id}",
    response_model=AssessmentResultVersionResponse,
)
def get_assessment_result_version(
    context: ReadContext, service: Service, result_id: UUID, version_id: UUID
) -> AssessmentResultVersionResponse:
    try:
        versions = service.list_versions(context.tenant_id, result_id)
        version = next((item for item in versions if item["id"] == version_id), None)
        if version is None:
            raise EntityNotFoundError("Assessment Results version not found.")
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error
    return AssessmentResultVersionResponse.model_validate(version)


@router.get("/assessment-results/{result_id}/versions/{version_id}/export")
def export_assessment_result_version(
    context: ReadContext, service: Service, result_id: UUID, version_id: UUID
) -> dict:
    try:
        return service.export_version(context.tenant_id, result_id, version_id)
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error

