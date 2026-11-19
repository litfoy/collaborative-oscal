from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response

from app.api.assessment_plan_schemas import (
    AssessmentPlanCreateInput,
    AssessmentPlanPublishInput,
    AssessmentPlanResponse,
    AssessmentPlanValidationResponse,
    AssessmentPlanVersionResponse,
    AssessmentPlanWorkingInput,
)
from app.api.dependencies import require_tenant_permission
from app.application.assessment_plans import (
    AssessmentPlanService,
    InvalidAssessmentPlan,
    StaleAssessmentPlanUpdate,
)
from app.domain.errors import EntityNotFoundError
from app.domain.identity.models import AuthorizedTenantContext, Permission
from app.persistence.database import create_session_factory

router = APIRouter(prefix="/api/v1/tenants/{tenant_id}", tags=["assessment-plans"])
ReadContext = Annotated[
    AuthorizedTenantContext, Depends(require_tenant_permission(Permission.CATALOG_READ))
]
WriteContext = Annotated[
    AuthorizedTenantContext, Depends(require_tenant_permission(Permission.CATALOG_WRITE))
]


def get_assessment_plan_service() -> AssessmentPlanService:
    return AssessmentPlanService(lambda: create_session_factory().begin())


Service = Annotated[AssessmentPlanService, Depends(get_assessment_plan_service)]


def _handle_not_found(error: EntityNotFoundError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(error))


def _handle_invalid(error: InvalidAssessmentPlan) -> HTTPException:
    return HTTPException(status_code=422, detail={"diagnostics": error.diagnostics})


def _handle_stale(error: StaleAssessmentPlanUpdate) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": "stale_update",
            "plan_id": str(error.plan_id),
            "expected_version": error.expected_version,
            "current_version": error.current_version,
        },
    )


@router.get("/systems/{system_id}/assessment-plans", response_model=list[AssessmentPlanResponse])
def list_assessment_plans(
    context: ReadContext, service: Service, system_id: UUID
) -> list[AssessmentPlanResponse]:
    try:
        return [
            AssessmentPlanResponse.model_validate(item)
            for item in service.list_plans(context.tenant_id, system_id)
        ]
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error


@router.post(
    "/systems/{system_id}/assessment-plans",
    response_model=AssessmentPlanResponse,
    status_code=201,
)
def create_assessment_plan(
    context: WriteContext,
    service: Service,
    system_id: UUID,
    request: AssessmentPlanCreateInput,
) -> AssessmentPlanResponse:
    try:
        result = service.create_plan(
            context.tenant_id,
            context.membership.user_id,
            system_id,
            ssp_version_id=request.ssp_version_id,
            title=request.title,
            description=request.description,
        )
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error
    except InvalidAssessmentPlan as error:
        raise _handle_invalid(error) from error
    return AssessmentPlanResponse.model_validate(result)


@router.get("/assessment-plans/{plan_id}", response_model=AssessmentPlanResponse)
def get_assessment_plan(
    context: ReadContext, service: Service, plan_id: UUID
) -> AssessmentPlanResponse:
    try:
        result = service.get_plan(context.tenant_id, plan_id)
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error
    return AssessmentPlanResponse.model_validate(result)


@router.put("/assessment-plans/{plan_id}", response_model=AssessmentPlanResponse)
def update_assessment_plan(
    context: WriteContext,
    service: Service,
    plan_id: UUID,
    request: AssessmentPlanWorkingInput,
) -> AssessmentPlanResponse:
    try:
        result = service.update_plan(
            context.tenant_id,
            context.membership.user_id,
            plan_id,
            expected_version=request.expected_version,
            title=request.title,
            description=request.description,
            working_data=request.model_dump(
                mode="json", exclude={"expected_version", "title", "description"}
            ),
        )
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error
    except InvalidAssessmentPlan as error:
        raise _handle_invalid(error) from error
    except StaleAssessmentPlanUpdate as error:
        raise _handle_stale(error) from error
    return AssessmentPlanResponse.model_validate(result)


@router.get(
    "/assessment-plans/{plan_id}/validation",
    response_model=AssessmentPlanValidationResponse,
)
def validate_assessment_plan(
    context: ReadContext, service: Service, plan_id: UUID
) -> AssessmentPlanValidationResponse:
    try:
        return AssessmentPlanValidationResponse.model_validate(
            service.validate_plan(context.tenant_id, plan_id)
        )
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error


@router.get(
    "/assessment-plans/{plan_id}/versions",
    response_model=list[AssessmentPlanVersionResponse],
)
def list_assessment_plan_versions(
    context: ReadContext, service: Service, plan_id: UUID
) -> list[AssessmentPlanVersionResponse]:
    try:
        return [
            AssessmentPlanVersionResponse.model_validate(item)
            for item in service.list_versions(context.tenant_id, plan_id)
        ]
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error


@router.post(
    "/assessment-plans/{plan_id}/versions",
    response_model=AssessmentPlanVersionResponse,
    status_code=201,
)
def create_assessment_plan_version(
    context: WriteContext,
    service: Service,
    plan_id: UUID,
    request: AssessmentPlanPublishInput,
    response: Response,
) -> AssessmentPlanVersionResponse:
    try:
        result = service.create_version(
            context.tenant_id,
            context.membership.user_id,
            plan_id,
            expected_version=request.expected_version,
        )
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error
    except InvalidAssessmentPlan as error:
        raise _handle_invalid(error) from error
    except StaleAssessmentPlanUpdate as error:
        raise _handle_stale(error) from error
    if not result["created"]:
        response.status_code = 200
    return AssessmentPlanVersionResponse.model_validate(result)


@router.get(
    "/assessment-plans/{plan_id}/versions/{version_id}",
    response_model=AssessmentPlanVersionResponse,
)
def get_assessment_plan_version(
    context: ReadContext, service: Service, plan_id: UUID, version_id: UUID
) -> AssessmentPlanVersionResponse:
    try:
        versions = service.list_versions(context.tenant_id, plan_id)
        version = next((item for item in versions if item["id"] == version_id), None)
        if version is None:
            raise EntityNotFoundError("Assessment Plan version not found.")
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error
    return AssessmentPlanVersionResponse.model_validate(version)


@router.get("/assessment-plans/{plan_id}/versions/{version_id}/export")
def export_assessment_plan_version(
    context: ReadContext, service: Service, plan_id: UUID, version_id: UUID
) -> dict:
    try:
        return service.export_version(context.tenant_id, plan_id, version_id)
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error
