from __future__ import annotations

from typing import Annotated
from uuid import UUID

from collaborative_oscal_oscal.mapping import (
    MappingDocumentValidationError,
    validate_mapping_document,
)
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from fastapi.responses import JSONResponse

from app.api.catalog_schemas import ErrorResponse
from app.api.dependencies import get_current_identity, require_tenant_permission
from app.api.mapping_schemas import (
    MappingCollectionInput,
    MappingCollectionListResponse,
    MappingCollectionResponse,
    RelatedControlResponse,
    RelatedMappingListResponse,
    RelatedMappingResponse,
)
from app.application.mappings import InvalidMapping, MappingService
from app.config import get_settings
from app.domain.errors import EntityNotFoundError
from app.domain.identity.models import AuthorizedTenantContext, Permission, UserIdentity
from app.domain.mappings import MappingEntrySpec, MappingPairSpec
from app.persistence.database import create_session_factory

router = APIRouter(prefix="/api/v1")

AUTH_ERRORS: dict[int | str, dict] = {
    401: {"model": ErrorResponse, "description": "Authentication required or invalid token."},
    403: {"model": ErrorResponse, "description": "Tenant access or permission denied."},
}
NOT_FOUND = {404: {"model": ErrorResponse, "description": "Resource not found in the tenant."}}

require_mapping_read = require_tenant_permission(Permission.CATALOG_READ)
require_mapping_write = require_tenant_permission(Permission.CATALOG_WRITE)
ReadContext = Annotated[AuthorizedTenantContext, Depends(require_mapping_read)]
WriteContext = Annotated[AuthorizedTenantContext, Depends(require_mapping_write)]
CollectionId = Annotated[UUID, Path(description="Mapping collection identifier within the tenant.")]
CatalogId = Annotated[UUID, Path(description="Catalog identifier within the tenant.")]
RevisionId = Annotated[UUID, Path(description="Immutable catalog revision identifier.")]


def _service() -> MappingService:
    return MappingService(lambda: create_session_factory().begin())


Service = Annotated[MappingService, Depends(_service)]
Identity = Annotated[UserIdentity, Depends(get_current_identity)]


def _page_params(
    limit: Annotated[int | None, Query(ge=1)] = None,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
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


def _specs(request: MappingCollectionInput) -> list[MappingPairSpec]:
    return [
        MappingPairSpec(
            item.id,
            item.source_catalog_id,
            item.source_revision_id,
            item.target_catalog_id,
            item.target_revision_id,
            tuple(
                MappingEntrySpec(
                    entry.id,
                    tuple(entry.sources),
                    tuple(entry.targets),
                    entry.relationship,
                    entry.matching_rationale,
                    entry.justification,
                )
                for entry in item.entries
            ),
        )
        for item in request.mappings
    ]


@router.get(
    "/tenants/{tenant_id}/mapping-collections",
    response_model=MappingCollectionListResponse,
    responses=AUTH_ERRORS,
    tags=["mappings"],
    summary="List Control Mapping collections in a tenant",
)
def list_mapping_collections(
    context: ReadContext,
    service: Service,
    pagination: Annotated[tuple[int, int], Depends(_page_params)],
) -> MappingCollectionListResponse:
    limit, offset = pagination
    page = service.list(context.tenant_id, limit=limit, offset=offset)
    return MappingCollectionListResponse(
        items=[MappingCollectionResponse.from_collection(item) for item in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.post(
    "/tenants/{tenant_id}/mapping-collections",
    response_model=MappingCollectionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        **AUTH_ERRORS,
        **NOT_FOUND,
        422: {"model": ErrorResponse, "description": "Invalid OSCAL mapping input."},
    },
    tags=["mappings"],
    summary="Create an OSCAL Control Mapping collection",
)
def create_mapping_collection(
    context: WriteContext,
    identity: Identity,
    service: Service,
    request: MappingCollectionInput,
) -> MappingCollectionResponse:
    try:
        collection = service.create(
            context.tenant_id,
            identity,
            request.title,
            request.description,
            _specs(request),
        )
    except EntityNotFoundError as error:
        raise _not_found(error) from error
    except (InvalidMapping, MappingDocumentValidationError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
    return MappingCollectionResponse.from_collection(collection)


@router.get(
    "/tenants/{tenant_id}/mapping-collections/{collection_id}",
    response_model=MappingCollectionResponse,
    responses={**AUTH_ERRORS, **NOT_FOUND},
    tags=["mappings"],
    summary="Get a Control Mapping collection",
)
def get_mapping_collection(
    context: ReadContext, service: Service, collection_id: CollectionId
) -> MappingCollectionResponse:
    try:
        return MappingCollectionResponse.from_collection(
            service.get(context.tenant_id, collection_id)
        )
    except EntityNotFoundError as error:
        raise _not_found(error) from error


@router.put(
    "/tenants/{tenant_id}/mapping-collections/{collection_id}",
    response_model=MappingCollectionResponse,
    responses={
        **AUTH_ERRORS,
        **NOT_FOUND,
        422: {"model": ErrorResponse, "description": "Invalid OSCAL mapping input."},
    },
    tags=["mappings"],
    summary="Update a Control Mapping collection",
)
def update_mapping_collection(
    context: WriteContext,
    identity: Identity,
    service: Service,
    collection_id: CollectionId,
    request: MappingCollectionInput,
) -> MappingCollectionResponse:
    try:
        collection = service.update(
            context.tenant_id,
            collection_id,
            identity,
            request.title,
            request.description,
            _specs(request),
        )
    except EntityNotFoundError as error:
        raise _not_found(error) from error
    except (InvalidMapping, MappingDocumentValidationError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
    return MappingCollectionResponse.from_collection(collection)


@router.delete(
    "/tenants/{tenant_id}/mapping-collections/{collection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**AUTH_ERRORS, **NOT_FOUND},
    tags=["mappings"],
    summary="Delete a Control Mapping collection",
)
def delete_mapping_collection(
    context: WriteContext, service: Service, collection_id: CollectionId
) -> Response:
    try:
        service.delete(context.tenant_id, collection_id)
    except EntityNotFoundError as error:
        raise _not_found(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/tenants/{tenant_id}/mapping-collections/{collection_id}/export",
    responses={**AUTH_ERRORS, **NOT_FOUND},
    tags=["mappings"],
    summary="Export a Control Mapping collection as OSCAL JSON",
)
def export_mapping_collection(
    context: ReadContext, service: Service, collection_id: CollectionId
) -> JSONResponse:
    try:
        collection = service.get(context.tenant_id, collection_id)
        validate_mapping_document(collection.document)
    except EntityNotFoundError as error:
        raise _not_found(error) from error
    except MappingDocumentValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
    filename = f"mapping-collection-{collection.id}.json"
    return JSONResponse(
        content=collection.document,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/tenants/{tenant_id}/catalogs/{catalog_id}/revisions/{revision_id}/controls/"
    "{control_id}/related-mappings",
    response_model=RelatedMappingListResponse,
    responses={**AUTH_ERRORS, **NOT_FOUND},
    tags=["mappings"],
    summary="List mappings explicitly related to a control in this revision",
)
def list_related_mappings(
    context: ReadContext,
    service: Service,
    catalog_id: CatalogId,
    revision_id: RevisionId,
    control_id: Annotated[str, Path(min_length=1, max_length=255)],
) -> RelatedMappingListResponse:
    try:
        related = service.related_controls(context.tenant_id, catalog_id, revision_id, control_id)
    except EntityNotFoundError as error:
        raise _not_found(error) from error
    return RelatedMappingListResponse(
        items=[
            RelatedMappingResponse(
                collection_id=item.collection_id,
                collection_title=item.collection_title,
                mapping_uuid=item.mapping_uuid,
                entry_uuid=item.entry_uuid,
                relationship=item.relationship,
                matching_rationale=item.matching_rationale,
                matched_side=item.matched_side,
                sources=[RelatedControlResponse.model_validate(member) for member in item.sources],
                targets=[RelatedControlResponse.model_validate(member) for member in item.targets],
            )
            for item in related
        ]
    )
