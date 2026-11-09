import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture(scope="session")
def postgres_url() -> str:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL integration tests.")
    parsed_url = make_url(database_url)
    if parsed_url.get_backend_name() != "postgresql":
        pytest.fail("PostgreSQL integration tests require a PostgreSQL URL.")
    if not parsed_url.database or not parsed_url.database.endswith("_test"):
        pytest.fail("TEST_DATABASE_URL must target a database whose name ends in '_test'.")
    return database_url


@pytest.fixture(scope="session")
def db_engine(postgres_url: str):
    engine = create_engine(postgres_url, pool_pre_ping=True)
    alembic_config = Config(str(Path(__file__).parents[3] / "alembic.ini"))
    alembic_config.attributes["database_url"] = postgres_url
    command.upgrade(alembic_config, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(db_engine) -> sessionmaker[Session]:
    return sessionmaker(bind=db_engine, expire_on_commit=False)


@pytest.fixture
def grc_service(session_factory):
    from app.application.services import GrcService
    from app.persistence.repositories import SQLAlchemyUnitOfWork

    return GrcService(lambda: SQLAlchemyUnitOfWork(session_factory))
