from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.catalog_import_routes import router as catalog_import_router
from app.api.catalog_routes import router as catalog_router
from app.api.implementation_routes import router as implementation_router
from app.api.profile_routes import router as profile_router
from app.api.routes import router as api_router
from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title="Collaborative OSCAL API",
    version="0.1.0",
    description=("Tenant-scoped OSCAL catalog exploration and basic profile authoring."),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Accept", "Authorization", "Content-Type"],
)
app.include_router(api_router)
app.include_router(catalog_router)
app.include_router(catalog_import_router)
app.include_router(profile_router)
app.include_router(implementation_router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
