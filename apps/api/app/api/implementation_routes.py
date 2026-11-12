from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.api.catalog_routes import Pagination, get_catalog_service
from app.api.catalog_schemas import ControlDetailResponse
from app.api.dependencies import require_tenant_permission
from app.api.implementation_schemas import (
    ImplementationCreate,
    ImplementationInformation,
    ImplementationOptions,
    ImplementationPage,
    ImplementationResponse,
    OrganizationOption,
    PersonOption,
)
from app.application.catalog_browsing import CatalogBrowsingService
from app.application.implementations import ImplementationService, InvalidImplementation
from app.domain.errors import EntityNotFoundError
from app.domain.identity.models import AuthorizedTenantContext, Permission
from app.domain.implementations import ImplementationInformation as Information
from app.domain.implementations import Responsibility
from app.persistence.database import create_session_factory

router = APIRouter(prefix="/api/v1/tenants/{tenant_id}", tags=["implementations"])
ReadContext = Annotated[
    AuthorizedTenantContext, Depends(require_tenant_permission(Permission.CATALOG_READ))
]
WriteContext = Annotated[
    AuthorizedTenantContext, Depends(require_tenant_permission(Permission.CATALOG_WRITE))
]


def get_implementation_service() -> ImplementationService:
    return ImplementationService(lambda: create_session_factory().begin())


Service = Annotated[ImplementationService, Depends(get_implementation_service)]
CatalogService = Annotated[CatalogBrowsingService, Depends(get_catalog_service)]


def _information(request: ImplementationInformation) -> Information:
    return Information(
        request.description,
        request.status,
        request.evidence_references,
        [Responsibility(r.kind, r.user_id, r.role) for r in request.responsibilities],
    )


def _not_found(error: EntityNotFoundError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(error))


@router.get("/implementation-options", response_model=ImplementationOptions)
def implementation_options(context: ReadContext, service: Service) -> ImplementationOptions:
    organizations, people = service.options(context.tenant_id)
    return ImplementationOptions(
        organizations=[OrganizationOption(id=id_, name=name) for id_, name in organizations],
        people=[PersonOption(id=id_, display_name=name) for id_, name in people],
    )


@router.get("/implementations", response_model=ImplementationPage)
def list_implementations(
    context: ReadContext,
    service: Service,
    pagination: Pagination,
    profile_id: UUID | None = None,
    organization_id: UUID | None = None,
    tenant_scope: bool = False,
) -> ImplementationPage:
    if tenant_scope and organization_id is not None:
        raise HTTPException(status_code=422, detail="Choose either tenant or organization scope.")
    page = service.list(
        context.tenant_id,
        profile_id=profile_id,
        organization_id=organization_id,
        tenant_scope=tenant_scope,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return ImplementationPage(
        items=[ImplementationResponse.model_validate(item) for item in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.post("/implementations", response_model=ImplementationResponse, status_code=201)
def create_implementation(
    context: WriteContext,
    service: Service,
    request: ImplementationCreate,
) -> ImplementationResponse:
    try:
        result = service.create(
            context.tenant_id,
            context.membership.user_id,
            request.catalog_id,
            request.revision_id,
            request.oscal_control_id,
            request.organization_id,
            request.profile_id,
            _information(request),
            request.profile_import_id,
        )
    except EntityNotFoundError as error:
        raise _not_found(error) from error
    except InvalidImplementation as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return ImplementationResponse.model_validate(result)


@router.get("/implementations/{implementation_id}", response_model=ImplementationResponse)
def get_implementation(
    context: ReadContext,
    service: Service,
    implementation_id: UUID,
) -> ImplementationResponse:
    try:
        return ImplementationResponse.model_validate(
            service.get(context.tenant_id, implementation_id)
        )
    except EntityNotFoundError as error:
        raise _not_found(error) from error


@router.put("/implementations/{implementation_id}", response_model=ImplementationResponse)
def update_implementation(
    context: WriteContext,
    service: Service,
    implementation_id: UUID,
    request: ImplementationInformation,
) -> ImplementationResponse:
    try:
        result = service.update(
            context.tenant_id, context.membership.user_id, implementation_id, _information(request)
        )
    except EntityNotFoundError as error:
        raise _not_found(error) from error
    except InvalidImplementation as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return ImplementationResponse.model_validate(result)


@router.get("/implementations/{implementation_id}/control", response_model=ControlDetailResponse)
def implementation_control(
    context: ReadContext,
    service: Service,
    catalog: CatalogService,
    implementation_id: UUID,
) -> ControlDetailResponse:
    try:
        record = service.get(context.tenant_id, implementation_id)
        return ControlDetailResponse.from_view(
            catalog.get_control(
                context.tenant_id, record.catalog_id, record.revision_id, record.oscal_control_id
            )
        )
    except EntityNotFoundError as error:
        raise _not_found(error) from error
