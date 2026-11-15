import logging

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api.catalog_import_routes import router as catalog_import_router
from app.api.catalog_routes import router as catalog_router
from app.api.component_definition_routes import router as component_definition_router
from app.api.implementation_routes import router as implementation_router
from app.api.mapping_routes import router as mapping_router
from app.api.profile_routes import router as profile_router
from app.api.routes import router as api_router
from app.api.system_security_plan_routes import router as system_security_plan_router
from app.config import get_settings

settings = get_settings()
component_definition_diagnostics = logging.getLogger("app.component_definition_diagnostics")
component_definition_diagnostics.setLevel(logging.WARNING)
if not any(
    isinstance(handler, logging.FileHandler)
    and handler.baseFilename == "/tmp/collaborative-oscal-component-definition.log"
    for handler in component_definition_diagnostics.handlers
):
    component_definition_diagnostics.addHandler(
        logging.FileHandler(
            "/tmp/collaborative-oscal-component-definition.log",
            mode="w",
            encoding="utf-8",
        )
    )

app = FastAPI(
    title="Collaborative OSCAL API",
    version="0.1.0",
    description=(
        "Tenant-scoped OSCAL catalog exploration, profile authoring, and Control Mappings."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Accept", "Authorization", "Content-Type"],
)
app.include_router(api_router)
app.include_router(catalog_router)
app.include_router(component_definition_router)
app.include_router(catalog_import_router)
app.include_router(profile_router)
app.include_router(implementation_router)
app.include_router(mapping_router)
app.include_router(system_security_plan_router)


@app.exception_handler(RequestValidationError)
async def log_component_definition_validation_error(
    request: Request, error: RequestValidationError
):
    if request.method == "PUT" and "/component-definitions/" in request.url.path:
        errors = [
            {
                "location": ".".join(str(item) for item in detail.get("loc", ())),
                "type": detail.get("type"),
                "message": detail.get("msg"),
            }
            for detail in error.errors()
        ]
        component_definition_diagnostics.warning(
            "Component Definition update request validation failed path=%s errors=%s",
            request.url.path,
            errors,
        )
    return await request_validation_exception_handler(request, error)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
