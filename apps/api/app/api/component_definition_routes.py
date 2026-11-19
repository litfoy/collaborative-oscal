# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

import logging
from typing import Annotated
from uuid import UUID

from collaborative_oscal_oscal.component_definition import (
    ComponentDefinitionValidationError,
    validate_component_definition_document,
)
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from fastapi.responses import JSONResponse

from app.api.catalog_schemas import ErrorResponse
from app.api.component_definition_schemas import (
    ComponentDefinitionCreateRequest,
    ComponentDefinitionPage,
    ComponentDefinitionResponse,
    ComponentDefinitionUpdateRequest,
    ComponentDefinitionValidationErrorResponse,
)
from app.api.dependencies import require_tenant_permission
from app.application.component_definitions import (
    ComponentDefinitionService,
    InvalidComponentDefinition,
    StaleComponentDefinitionUpdate,
)
from app.config import get_settings
from app.domain.errors import EntityNotFoundError
from app.domain.identity.models import AuthorizedTenantContext, Permission
from app.persistence.database import create_session_factory

router = APIRouter(prefix="/api/v1")
logger = logging.getLogger("app.component_definition_diagnostics")

AUTH_ERRORS: dict[int | str, dict] = {
    401: {"model": ErrorResponse, "description": "Authentication required or invalid token."},
    403: {"model": ErrorResponse, "description": "Tenant access or permission denied."},
}
NOT_FOUND = {404: {"model": ErrorResponse, "description": "Resource not found in the tenant."}}

ReadContext = Annotated[
    AuthorizedTenantContext,
    Depends(require_tenant_permission(Permission.CATALOG_READ)),
]
WriteContext = Annotated[
    AuthorizedTenantContext,
    Depends(require_tenant_permission(Permission.CATALOG_WRITE)),
]
DocumentId = Annotated[UUID, Path(description="Component Definition identifier in the tenant.")]
ComponentId = Annotated[UUID, Path(description="Stable internal component identifier.")]


def get_component_definition_service() -> ComponentDefinitionService:
    return ComponentDefinitionService(lambda: create_session_factory().begin())


Service = Annotated[ComponentDefinitionService, Depends(get_component_definition_service)]


def _not_found(error: EntityNotFoundError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(error))


def _page_params(limit: int | None, offset: int) -> tuple[int, int]:
    settings = get_settings()
    resolved = settings.api_page_size_default if limit is None else limit
    if resolved > settings.api_page_size_max:
        raise HTTPException(
            status_code=422, detail=f"limit must not exceed {settings.api_page_size_max}."
        )
    return resolved, offset


def _stale(error: StaleComponentDefinitionUpdate) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "stale_update",
            "document_id": str(error.document_id),
            "expected_version": error.expected_version,
            "current_version": error.current_version,
        },
    )


@router.get(
    "/tenants/{tenant_id}/component-definitions",
    response_model=ComponentDefinitionPage,
    responses=AUTH_ERRORS,
    tags=["component-definitions"],
)
def list_component_definitions(
    context: ReadContext,
    service: Service,
    limit: Annotated[int | None, Query(ge=1)] = None,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> ComponentDefinitionPage:
    limit, offset = _page_params(limit, offset)
    page = service.list(context.tenant_id, limit=limit, offset=offset)
    return ComponentDefinitionPage(
        items=[ComponentDefinitionResponse.from_definition(item) for item in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.post(
    "/tenants/{tenant_id}/component-definitions",
    response_model=ComponentDefinitionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        **AUTH_ERRORS,
        **NOT_FOUND,
        409: {"model": ErrorResponse, "description": "Component Definition changed after load."},
        422: {
            "model": ComponentDefinitionValidationErrorResponse,
            "description": "Invalid Component Definition input.",
        },
    },
    tags=["component-definitions"],
)
def create_component_definition(
    context: WriteContext,
    service: Service,
    request: ComponentDefinitionCreateRequest,
) -> ComponentDefinitionResponse:
    try:
        definition = service.create(
            context.tenant_id,
            context.membership.user_id,
            request.title,
            request.type,
            request.description,
            [item.to_domain() for item in request.requirements],
        )
    except EntityNotFoundError as error:
        raise _not_found(error) from error
    except (InvalidComponentDefinition, ComponentDefinitionValidationError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return ComponentDefinitionResponse.from_definition(definition)


@router.get(
    "/tenants/{tenant_id}/component-definitions/{document_id}",
    response_model=ComponentDefinitionResponse,
    responses={**AUTH_ERRORS, **NOT_FOUND},
    tags=["component-definitions"],
)
def get_component_definition(
    context: ReadContext, service: Service, document_id: DocumentId
) -> ComponentDefinitionResponse:
    try:
        return ComponentDefinitionResponse.from_definition(
            service.get(context.tenant_id, document_id)
        )
    except EntityNotFoundError as error:
        raise _not_found(error) from error


@router.put(
    "/tenants/{tenant_id}/component-definitions/{document_id}",
    response_model=ComponentDefinitionResponse,
    responses={
        **AUTH_ERRORS,
        **NOT_FOUND,
        422: {
            "model": ComponentDefinitionValidationErrorResponse,
            "description": "Invalid Component Definition input.",
        },
    },
    tags=["component-definitions"],
)
def update_component_definition(
    context: WriteContext,
    service: Service,
    document_id: DocumentId,
    request: ComponentDefinitionUpdateRequest,
) -> ComponentDefinitionResponse:
    try:
        definition = service.update(
            context.tenant_id,
            context.membership.user_id,
            document_id,
            request.expected_version,
            request.title,
            [item.to_domain() for item in request.components],
        )
    except EntityNotFoundError as error:
        raise _not_found(error) from error
    except StaleComponentDefinitionUpdate as error:
        raise _stale(error) from error
    except (InvalidComponentDefinition, ComponentDefinitionValidationError) as error:
        logger.warning(
            "Component Definition update rejected tenant_id=%s document_id=%s reason=%s",
            context.tenant_id,
            document_id,
            error,
        )
        raise HTTPException(status_code=422, detail=str(error)) from error
    return ComponentDefinitionResponse.from_definition(definition)


@router.delete(
    "/tenants/{tenant_id}/component-definitions/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        **AUTH_ERRORS,
        **NOT_FOUND,
        409: {"model": ErrorResponse, "description": "Component Definition changed after load."},
    },
    tags=["component-definitions"],
)
def delete_component_definition(
    context: WriteContext,
    service: Service,
    document_id: DocumentId,
    expected_version: int = Query(ge=1),
) -> Response:
    try:
        service.delete(
            context.tenant_id,
            document_id,
            expected_version=expected_version,
        )
    except EntityNotFoundError as error:
        raise _not_found(error) from error
    except StaleComponentDefinitionUpdate as error:
        raise _stale(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/tenants/{tenant_id}/component-definitions/{document_id}/components/{component_id}",
    response_model=ComponentDefinitionResponse,
    status_code=status.HTTP_200_OK,
    responses={
        **AUTH_ERRORS,
        **NOT_FOUND,
        409: {"model": ErrorResponse, "description": "Component Definition changed after load."},
        204: {"description": "The last component deleted the whole document."},
    },
    tags=["component-definitions"],
)
def delete_component(
    context: WriteContext,
    service: Service,
    document_id: DocumentId,
    component_id: ComponentId,
    expected_version: int = Query(ge=1),
) -> ComponentDefinitionResponse | Response:
    try:
        updated = service.delete_component(
            context.tenant_id,
            context.membership.user_id,
            document_id,
            component_id,
            expected_version=expected_version,
        )
    except EntityNotFoundError as error:
        raise _not_found(error) from error
    except StaleComponentDefinitionUpdate as error:
        raise _stale(error) from error
    if updated is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return ComponentDefinitionResponse.from_definition(updated)


@router.get(
    "/tenants/{tenant_id}/component-definitions/{document_id}/export",
    responses={**AUTH_ERRORS, **NOT_FOUND},
    tags=["component-definitions"],
)
def export_component_definition(
    context: ReadContext, service: Service, document_id: DocumentId
) -> JSONResponse:
    try:
        document = service.export(context.tenant_id, document_id)
        validate_component_definition_document(document)
    except EntityNotFoundError as error:
        raise _not_found(error) from error
    except ComponentDefinitionValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return JSONResponse(
        content=document,
        headers={
            "Content-Disposition": (
                f'attachment; filename="component-definition-{document_id}.json"'
            )
        },
    )
