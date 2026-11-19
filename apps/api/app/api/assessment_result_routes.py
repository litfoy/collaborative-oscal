# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response

from app.api.assessment_result_schemas import (
    AssessmentResultCreateInput,
    AssessmentResultPublishInput,
    AssessmentResultResponse,
    AssessmentResultValidationResponse,
    AssessmentResultVersionResponse,
    AssessmentResultWorkingInput,
)
from app.api.dependencies import require_tenant_permission
from app.application.assessment_results import (
    AssessmentResultImportConflict,
    AssessmentResultService,
    InvalidAssessmentResult,
    StaleAssessmentResultUpdate,
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


def _handle_stale(error: StaleAssessmentResultUpdate) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": "stale_update",
            "result_id": str(error.result_id),
            "expected_version": error.expected_version,
            "current_version": error.current_version,
        },
    )


def _handle_import_conflict(error: AssessmentResultImportConflict) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": "import_conflict",
            "reason": error.reason,
            "source_document_uuid": str(error.source_document_uuid),
            "existing_result_id": str(error.existing_result_id),
            "existing_assessment_plan_id": str(error.existing_assessment_plan_id),
            "existing_assessment_plan_version_id": str(error.existing_assessment_plan_version_id),
        },
    )


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
            expected_version=request.expected_version,
            title=request.title,
            description=request.description,
            working_data=request.model_dump(
                mode="json", exclude={"expected_version", "title", "description"}
            ),
        )
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error
    except InvalidAssessmentResult as error:
        raise _handle_invalid(error) from error
    except StaleAssessmentResultUpdate as error:
        raise _handle_stale(error) from error
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
    "/assessment-plans/{plan_id}/versions/{version_id}/assessment-results/import",
    response_model=AssessmentResultResponse,
    status_code=201,
)
def import_assessment_result(
    context: WriteContext,
    service: Service,
    plan_id: UUID,
    version_id: UUID,
    document: dict[str, Any],
    response: Response,
) -> AssessmentResultResponse:
    try:
        result, created = service.import_result(
            context.tenant_id,
            context.membership.user_id,
            assessment_plan_id=plan_id,
            assessment_plan_version_id=version_id,
            document=document,
        )
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error
    except InvalidAssessmentResult as error:
        raise _handle_invalid(error) from error
    except AssessmentResultImportConflict as error:
        raise _handle_import_conflict(error) from error
    if not created:
        response.status_code = 200
    return AssessmentResultResponse.model_validate(result)


@router.post(
    "/assessment-results/{result_id}/versions",
    response_model=AssessmentResultVersionResponse,
    status_code=201,
)
def create_assessment_result_version(
    context: WriteContext,
    service: Service,
    result_id: UUID,
    request: AssessmentResultPublishInput,
    response: Response,
) -> AssessmentResultVersionResponse:
    try:
        result = service.create_version(
            context.tenant_id,
            context.membership.user_id,
            result_id,
            expected_version=request.expected_version,
        )
    except EntityNotFoundError as error:
        raise _handle_not_found(error) from error
    except InvalidAssessmentResult as error:
        raise _handle_invalid(error) from error
    except StaleAssessmentResultUpdate as error:
        raise _handle_stale(error) from error
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

