from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.catalog_routes import router as catalog_router
from app.api.routes import router as api_router
from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title="Collaborative OSCAL API",
    version="0.1.0",
    description="API foundation with a read-only, tenant-scoped OSCAL catalog explorer.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api_cors_origins,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["Accept", "Authorization", "Content-Type"],
)
app.include_router(api_router)
app.include_router(catalog_router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
