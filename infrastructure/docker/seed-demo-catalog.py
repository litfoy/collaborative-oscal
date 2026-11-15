import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import sessionmaker

from app.application.catalog_import import CatalogImportMetadata, CatalogImportService
from app.authentication.demo import DEMO_TENANT_ID
from app.config import get_settings
from app.persistence.models import CatalogRevisionRecord
from app.persistence.repositories import SQLAlchemyUnitOfWork

CATALOG_PATH = Path("/opt/demo/nist-sp-800-53-rev5.json")
CATALOG_UUID = UUID("ea7c7688-79c5-463b-a91b-0650f2d98623")
SEED_NAME = "nist-sp-800-53-rev5"
SOURCE_URI = "https://github.com/usnistgov/oscal-content/releases/tag/v1.5.0"


def seed_catalog(connection: Connection, catalog_path: Path) -> bool:
    if get_settings().auth_mode != "demo":
        raise RuntimeError("Demo catalog seeding requires AUTH_MODE=demo.")

    connection.execute(text("SELECT pg_advisory_xact_lock(5506136920904621)"))
    connection.execute(
        text("CREATE TABLE IF NOT EXISTS compose_demo_seeds (name TEXT PRIMARY KEY)")
    )
    if connection.execute(
        text("SELECT 1 FROM compose_demo_seeds WHERE name = :name"), {"name": SEED_NAME}
    ).first():
        return False

    existing = connection.execute(
        select(CatalogRevisionRecord.id).where(
            CatalogRevisionRecord.tenant_id == DEMO_TENANT_ID,
            CatalogRevisionRecord.oscal_document_uuid == CATALOG_UUID,
        )
    ).first()
    if not existing:
        content = catalog_path.read_bytes()
        if UUID(json.loads(content)["catalog"]["uuid"]) != CATALOG_UUID:
            raise ValueError("The bundled NIST catalog has an unexpected document UUID.")
        factory = sessionmaker(bind=connection, join_transaction_mode="create_savepoint")
        service = CatalogImportService(lambda: SQLAlchemyUnitOfWork(factory))
        service.import_catalog(
            DEMO_TENANT_ID,
            content,
            metadata=CatalogImportMetadata(
                source_uri=SOURCE_URI,
                source_organization="National Institute of Standards and Technology",
            ),
        )

    connection.execute(
        text("INSERT INTO compose_demo_seeds (name) VALUES (:name)"), {"name": SEED_NAME}
    )
    return not bool(existing)


def main() -> None:
    engine = create_engine(get_settings().get_database_url(), pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            created = seed_catalog(connection, CATALOG_PATH)
    finally:
        engine.dispose()
    print("Demo NIST catalog imported." if created else "Demo NIST catalog seed already applied.")


if __name__ == "__main__":
    main()
