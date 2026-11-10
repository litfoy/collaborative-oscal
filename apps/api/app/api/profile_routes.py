from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from fastapi.responses import JSONResponse

from app.api.catalog_schemas import ErrorResponse
from app.api.dependencies import require_tenant_permission
from app.api.profile_schemas import (
    ProfileCreateRequest,
    ProfileListResponse,
    ProfileResponse,
    ProfileUpdateRequest,
    ProfileValidationErrorResponse,
)
from app.application.profiles import InvalidProfileSelection, ProfileService
from app.config import get_settings
from app.domain.errors import EntityNotFoundError
from app.domain.identity.models import AuthorizedTenantContext, Permission
from app.persistence.database import create_session_factory

router = APIRouter(prefix="/api/v1")

AUTH_ERRORS: dict[int | str, dict] = {
    401: {"model": ErrorResponse, "description": "Authentication required or invalid token."},
    403: {"model": ErrorResponse, "description": "Tenant access or permission denied."},
}
NOT_FOUND = {404: {"model": ErrorResponse, "description": "Resource not found in the tenant."}}

require_profile_read = require_tenant_permission(Permission.CATALOG_READ)
require_profile_write = require_tenant_permission(Permission.CATALOG_WRITE)
ProfileReadContext = Annotated[AuthorizedTenantContext, Depends(require_profile_read)]
ProfileWriteContext = Annotated[AuthorizedTenantContext, Depends(require_profile_write)]
ProfileId = Annotated[UUID, Path(description="Profile identifier within the tenant.")]


def get_profile_service() -> ProfileService:
    return ProfileService(lambda: create_session_factory().begin())


Service = Annotated[ProfileService, Depends(get_profile_service)]


def _page_params(
    limit: int | None = None,
    offset: int = 0,
) -> tuple[int, int]:
    settings = get_settings()
    resolved = settings.api_page_size_default if limit is None else limit
    if resolved > settings.api_page_size_max:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"limit must not exceed {settings.api_page_size_max}.",
        )
    return resolved, offset


def _not_found(error: EntityNotFoundError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))


@router.get(
    "/tenants/{tenant_id}/profiles",
    response_model=ProfileListResponse,
    responses=AUTH_ERRORS,
    tags=["profiles"],
    summary="List profiles in a tenant",
)
def list_profiles(
    context: ProfileReadContext,
    service: Service,
    limit: Annotated[int | None, Query(ge=1)] = None,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> ProfileListResponse:
    limit, offset = _page_params(limit, offset)
    page = service.list(context.tenant_id, limit=limit, offset=offset)
    return ProfileListResponse(
        items=[ProfileResponse.from_profile(profile) for profile in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.post(
    "/tenants/{tenant_id}/profiles",
    response_model=ProfileResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        **AUTH_ERRORS,
        **NOT_FOUND,
        422: {"model": ProfileValidationErrorResponse, "description": "Invalid profile input."},
    },
    tags=["profiles"],
    summary="Create a profile selecting controls from an immutable catalog revision",
)
def create_profile(
    context: ProfileWriteContext, service: Service, request: ProfileCreateRequest
) -> ProfileResponse:
    try:
        profile = service.create(
            context.tenant_id,
            request.catalog_id,
            request.revision_id,
            request.title,
            request.control_ids,
            request.description,
        )
    except EntityNotFoundError as error:
        raise _not_found(error) from error
    except InvalidProfileSelection as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
    return ProfileResponse.from_profile(profile)


@router.get(
    "/tenants/{tenant_id}/profiles/{profile_id}",
    response_model=ProfileResponse,
    responses={**AUTH_ERRORS, **NOT_FOUND},
    tags=["profiles"],
    summary="Get profile metadata and its source reference",
)
def get_profile(
    context: ProfileReadContext, service: Service, profile_id: ProfileId
) -> ProfileResponse:
    try:
        return ProfileResponse.from_profile(service.get(context.tenant_id, profile_id))
    except EntityNotFoundError as error:
        raise _not_found(error) from error


@router.get(
    "/tenants/{tenant_id}/profiles/{profile_id}/export",
    responses={**AUTH_ERRORS, **NOT_FOUND},
    tags=["profiles"],
    summary="Export a profile as OSCAL JSON",
)
def export_profile(
    context: ProfileReadContext, service: Service, profile_id: ProfileId
) -> JSONResponse:
    try:
        profile = service.get(context.tenant_id, profile_id)
    except EntityNotFoundError as error:
        raise _not_found(error) from error
    return JSONResponse(content=profile.document)


@router.put(
    "/tenants/{tenant_id}/profiles/{profile_id}",
    response_model=ProfileResponse,
    responses={
        **AUTH_ERRORS,
        **NOT_FOUND,
        422: {"model": ProfileValidationErrorResponse, "description": "Invalid profile input."},
    },
    tags=["profiles"],
    summary="Update profile title and selected controls",
)
def update_profile(
    context: ProfileWriteContext,
    service: Service,
    profile_id: ProfileId,
    request: ProfileUpdateRequest,
) -> ProfileResponse:
    try:
        profile = service.update(
            context.tenant_id, profile_id, request.title, request.control_ids, request.description
        )
    except EntityNotFoundError as error:
        raise _not_found(error) from error
    except InvalidProfileSelection as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
    return ProfileResponse.from_profile(profile)
