from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import require_tenant_permission
from app.application.catalog_import import (
    CatalogImportService,
    CatalogImportValidationError,
)
from app.config import get_settings
from app.domain.errors import EntityNotFoundError
from app.domain.identity.models import AuthorizedTenantContext, Permission
from app.persistence.database import create_unit_of_work_factory

router = APIRouter(prefix="/api/v1", tags=["catalogs"])
require_catalog_import = require_tenant_permission(Permission.CATALOG_IMPORT)
ImportContext = Annotated[AuthorizedTenantContext, Depends(require_catalog_import)]


class ImportResponse(BaseModel):
    catalog_id: UUID
    catalog_name: str
    revision_id: UUID
    revision_number: int
    oscal_document_uuid: UUID
    oscal_version: str
    source_version: str | None
    control_count: int
    created: bool


async def _import(
    request: Request, context: AuthorizedTenantContext, catalog_id: UUID | None
) -> ImportResponse:
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != (
        "application/json"
    ):
        raise HTTPException(status_code=415, detail="Upload an OSCAL Catalog JSON file.")
    limit = get_settings().catalog_import_max_input_bytes
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > limit:
            raise HTTPException(status_code=413, detail=f"File exceeds the {limit}-byte limit.")
        content.extend(chunk)
    service = CatalogImportService(create_unit_of_work_factory(), max_input_bytes=limit)
    try:
        result = await run_in_threadpool(
            service.import_catalog,
            context.tenant_id,
            bytes(content),
            "json",
            target_catalog_id=catalog_id,
        )
    except CatalogImportValidationError as error:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Catalog validation failed.",
                "errors": [
                    {"code": issue.code, "message": issue.message, "path": issue.path}
                    for issue in error.result.errors[:20]
                ],
            },
        ) from error
    except EntityNotFoundError as error:
        raise HTTPException(status_code=404, detail="Catalog not found in this tenant.") from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Catalog metadata is invalid.") from error
    return ImportResponse(
        catalog_id=result.catalog.id,
        catalog_name=result.catalog.name,
        revision_id=result.revision.id,
        revision_number=result.revision.revision_number,
        oscal_document_uuid=result.revision.oscal_document_uuid,
        oscal_version=result.revision.oscal_version,
        source_version=result.revision.source_version,
        control_count=result.control_count,
        created=result.created,
    )


@router.post("/tenants/{tenant_id}/catalogs/import", response_model=ImportResponse)
async def import_new_catalog(request: Request, context: ImportContext) -> ImportResponse:
    return await _import(request, context, None)


@router.post("/tenants/{tenant_id}/catalogs/{catalog_id}/import", response_model=ImportResponse)
async def import_catalog_revision(
    request: Request, context: ImportContext, catalog_id: UUID
) -> ImportResponse:
    return await _import(request, context, catalog_id)
