from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from fastapi.responses import JSONResponse

from app.api.catalog_schemas import (
    CatalogListResponse,
    CatalogResponse,
    ControlDetailResponse,
    ControlListItemResponse,
    ControlListResponse,
    ErrorResponse,
    OutlineNodeResponse,
    OutlineResponse,
    RevisionDetailResponse,
    RevisionListResponse,
    RevisionSummaryResponse,
    TenantListResponse,
    TenantResponse,
    page_fields,
)
from app.api.dependencies import get_current_identity, require_tenant_permission
from app.application.authorization import list_accessible_tenants
from app.application.catalog_browsing import CatalogBrowsingService
from app.config import get_settings
from app.domain.catalogs.models import CatalogRevisionStatus
from app.domain.catalogs.read_models import OutlineNodeKind
from app.domain.errors import EntityNotFoundError
from app.domain.identity.models import AuthorizedTenantContext, Permission, UserIdentity
from app.persistence.database import create_session_factory
from app.persistence.identity import SQLMembershipRepository

router = APIRouter(prefix="/api/v1")

AUTH_ERRORS: dict[int | str, dict] = {
    401: {"model": ErrorResponse, "description": "Authentication required or invalid token."},
    403: {"model": ErrorResponse, "description": "Tenant access or permission denied."},
}
NOT_FOUND: dict[int | str, dict] = {
    404: {"model": ErrorResponse, "description": "Resource not found in the tenant."}
}

require_catalog_read = require_tenant_permission(Permission.CATALOG_READ)
TenantContext = Annotated[AuthorizedTenantContext, Depends(require_catalog_read)]
CatalogId = Annotated[UUID, Path(description="Catalog identifier within the tenant.")]
RevisionId = Annotated[UUID, Path(description="Catalog revision identifier.")]


@dataclass(frozen=True, slots=True)
class PageParams:
    limit: int
    offset: int


def page_params(
    limit: Annotated[
        int | None, Query(ge=1, description="Page size; bounded by the server.")
    ] = None,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> PageParams:
    settings = get_settings()
    resolved = settings.api_page_size_default if limit is None else limit
    if resolved > settings.api_page_size_max:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"limit must not exceed {settings.api_page_size_max}.",
        )
    return PageParams(resolved, offset)


def get_catalog_service() -> CatalogBrowsingService:
    return CatalogBrowsingService(lambda: create_session_factory().begin())


Service = Annotated[CatalogBrowsingService, Depends(get_catalog_service)]
Pagination = Annotated[PageParams, Depends(page_params)]
SearchText = Annotated[str | None, Query(max_length=200)]


def _not_found(error: EntityNotFoundError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))


@router.get(
    "/tenants",
    response_model=TenantListResponse,
    responses=AUTH_ERRORS,
    tags=["tenants"],
    summary="List tenants the caller has an active membership in",
)
def list_tenants(identity: UserIdentity = Depends(get_current_identity)) -> TenantListResponse:
    with create_session_factory().begin() as session:
        accessible = list_accessible_tenants(SQLMembershipRepository(session), identity.id)
    return TenantListResponse(items=[TenantResponse.from_access(item) for item in accessible])


@router.get(
    "/tenants/{tenant_id}/catalogs",
    response_model=CatalogListResponse,
    responses=AUTH_ERRORS,
    tags=["catalogs"],
    summary="List catalogs in a tenant",
)
def list_catalogs(
    context: TenantContext,
    service: Service,
    pagination: Pagination,
    q: SearchText = None,
) -> CatalogListResponse:
    page = service.list_catalogs(
        context.tenant_id, query=q, limit=pagination.limit, offset=pagination.offset
    )
    return CatalogListResponse(
        items=[CatalogResponse.from_summary(item) for item in page.items], **page_fields(page)
    )


@router.get(
    "/tenants/{tenant_id}/catalogs/{catalog_id}",
    response_model=CatalogResponse,
    responses={**AUTH_ERRORS, **NOT_FOUND},
    tags=["catalogs"],
    summary="Get catalog metadata and its latest revision",
)
def get_catalog(context: TenantContext, service: Service, catalog_id: CatalogId) -> CatalogResponse:
    try:
        return CatalogResponse.from_summary(service.get_catalog(context.tenant_id, catalog_id))
    except EntityNotFoundError as error:
        raise _not_found(error) from error


@router.get(
    "/tenants/{tenant_id}/catalogs/{catalog_id}/revisions",
    response_model=RevisionListResponse,
    responses={**AUTH_ERRORS, **NOT_FOUND},
    tags=["catalogs"],
    summary="List catalog revisions, newest first",
)
def list_revisions(
    context: TenantContext,
    service: Service,
    pagination: Pagination,
    catalog_id: CatalogId,
    lifecycle_status: Annotated[CatalogRevisionStatus | None, Query()] = None,
) -> RevisionListResponse:
    try:
        page = service.list_revisions(
            context.tenant_id,
            catalog_id,
            status=lifecycle_status,
            limit=pagination.limit,
            offset=pagination.offset,
        )
    except EntityNotFoundError as error:
        raise _not_found(error) from error
    return RevisionListResponse(
        items=[RevisionSummaryResponse.from_summary(item) for item in page.items],
        **page_fields(page),
    )


@router.get(
    "/tenants/{tenant_id}/catalogs/{catalog_id}/revisions/{revision_id}",
    response_model=RevisionDetailResponse,
    responses={**AUTH_ERRORS, **NOT_FOUND},
    tags=["catalogs"],
    summary="Get one catalog revision with source document metadata",
)
def get_revision(
    context: TenantContext, service: Service, catalog_id: CatalogId, revision_id: RevisionId
) -> RevisionDetailResponse:
    try:
        return RevisionDetailResponse.from_detail(
            service.get_revision(context.tenant_id, catalog_id, revision_id)
        )
    except EntityNotFoundError as error:
        raise _not_found(error) from error


@router.get(
    "/tenants/{tenant_id}/catalogs/{catalog_id}/revisions/{revision_id}/export",
    responses={**AUTH_ERRORS, **NOT_FOUND},
    tags=["catalogs"],
    summary="Export one immutable catalog revision as OSCAL JSON",
)
def export_revision(
    context: TenantContext, service: Service, catalog_id: CatalogId, revision_id: RevisionId
) -> JSONResponse:
    try:
        document = service.get_revision_document(context.tenant_id, catalog_id, revision_id)
    except EntityNotFoundError as error:
        raise _not_found(error) from error
    return JSONResponse(content=document)


@router.get(
    "/tenants/{tenant_id}/catalogs/{catalog_id}/revisions/{revision_id}/outline",
    response_model=OutlineResponse,
    responses={**AUTH_ERRORS, **NOT_FOUND},
    tags=["catalogs"],
    summary="List the direct children of a catalog, group, or control",
    description=(
        "Lazy hierarchy navigation. Omit `parent_kind` and `parent_id` for the catalog "
        "root. Controls are listed before groups, each in document order."
    ),
)
def list_outline(
    context: TenantContext,
    service: Service,
    pagination: Pagination,
    catalog_id: CatalogId,
    revision_id: RevisionId,
    parent_kind: Annotated[OutlineNodeKind | None, Query()] = None,
    parent_id: Annotated[UUID | None, Query()] = None,
) -> OutlineResponse:
    if (parent_kind is None) != (parent_id is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="parent_kind and parent_id must be provided together.",
        )
    try:
        page = service.list_outline(
            context.tenant_id,
            catalog_id,
            revision_id,
            parent_kind=parent_kind,
            parent_id=parent_id,
            limit=pagination.limit,
            offset=pagination.offset,
        )
    except EntityNotFoundError as error:
        raise _not_found(error) from error
    return OutlineResponse(
        items=[OutlineNodeResponse.from_node(item) for item in page.items], **page_fields(page)
    )


@router.get(
    "/tenants/{tenant_id}/catalogs/{catalog_id}/revisions/{revision_id}/controls",
    response_model=ControlListResponse,
    responses={**AUTH_ERRORS, **NOT_FOUND},
    tags=["catalogs"],
    summary="List or search controls in one revision",
    description="`q` matches a case-insensitive substring of the control ID or title.",
)
def list_controls(
    context: TenantContext,
    service: Service,
    pagination: Pagination,
    catalog_id: CatalogId,
    revision_id: RevisionId,
    q: SearchText = None,
) -> ControlListResponse:
    try:
        page = service.search_controls(
            context.tenant_id,
            catalog_id,
            revision_id,
            query=q.strip() if q and q.strip() else None,
            limit=pagination.limit,
            offset=pagination.offset,
        )
    except EntityNotFoundError as error:
        raise _not_found(error) from error
    return ControlListResponse(
        items=[
            ControlListItemResponse.from_item(item, catalog_id, revision_id) for item in page.items
        ],
        **page_fields(page),
    )


@router.get(
    "/tenants/{tenant_id}/catalogs/{catalog_id}/revisions/{revision_id}/controls/{control_id}",
    response_model=ControlDetailResponse,
    response_model_by_alias=True,
    responses={**AUTH_ERRORS, **NOT_FOUND},
    tags=["catalogs"],
    summary="Get a control by its OSCAL control ID within one revision",
    description=(
        "`control_id` is the OSCAL control `id` (an OSCAL token, never containing `/`). "
        "The stable source identity is catalog ID + revision ID + OSCAL control ID, "
        "returned as `reference`."
    ),
)
def get_control(
    context: TenantContext,
    service: Service,
    catalog_id: CatalogId,
    revision_id: RevisionId,
    control_id: Annotated[str, Path(min_length=1, max_length=255)],
) -> ControlDetailResponse:
    try:
        view = service.get_control(context.tenant_id, catalog_id, revision_id, control_id)
    except EntityNotFoundError as error:
        raise _not_found(error) from error
    return ControlDetailResponse.from_view(view)
