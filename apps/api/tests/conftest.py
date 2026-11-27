# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.persistence.database_roles import (
    OWNER_ROLE,
    PROVISIONER_ROLE,
    RUNTIME_ROLE,
    apply_privileges,
    create_role_engine,
)
from tests.database_role_harness import (
    MISSING_CONFIGURATION,
    REQUIRE_OPTION,
    OwnerCleanup,
    RoleHarnessConfigurationError,
    load_role_urls,
    same_database,
)

ALEMBIC_INI = Path(__file__).parents[3] / "alembic.ini"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        REQUIRE_OPTION,
        action="store_true",
        default=False,
        help="Fail, instead of skipping, separate-role PostgreSQL tests when unconfigured.",
    )


def _configured_role_urls() -> dict[str, str] | None:
    try:
        return load_role_urls()
    except RoleHarnessConfigurationError as error:
        pytest.fail(str(error))


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


# --- Separate-role harness (ADR 0029 §8, milestone 29.1a) -----------------------------------


@pytest.fixture(scope="session")
def database_role_urls(request: pytest.FixtureRequest) -> dict[str, str]:
    urls = _configured_role_urls()
    if urls is None:
        if request.config.getoption(REQUIRE_OPTION):
            pytest.fail(MISSING_CONFIGURATION)
        pytest.skip(MISSING_CONFIGURATION)
    return urls


@pytest.fixture(scope="session")
def owner_engine(database_role_urls: dict[str, str]) -> Iterator[Engine]:
    """Owner engine; migrates the _test database to head and applies the privilege contract."""
    engine = create_role_engine(database_role_urls[OWNER_ROLE], OWNER_ROLE, pool_pre_ping=True)
    alembic_config = Config(str(ALEMBIC_INI))
    alembic_config.attributes["database_url"] = database_role_urls[OWNER_ROLE]
    alembic_config.attributes["expected_role"] = OWNER_ROLE
    command.upgrade(alembic_config, "head")
    with engine.begin() as connection:
        apply_privileges(connection)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def runtime_engine(database_role_urls: dict[str, str], owner_engine: Engine) -> Iterator[Engine]:
    engine = create_role_engine(database_role_urls[RUNTIME_ROLE], RUNTIME_ROLE, pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def provisioner_engine(
    database_role_urls: dict[str, str], owner_engine: Engine
) -> Iterator[Engine]:
    engine = create_role_engine(
        database_role_urls[PROVISIONER_ROLE], PROVISIONER_ROLE, pool_pre_ping=True
    )
    yield engine
    engine.dispose()


@pytest.fixture
def owner_session_factory(owner_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=owner_engine, expire_on_commit=False)


@pytest.fixture
def runtime_session_factory(runtime_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=runtime_engine, expire_on_commit=False)


@pytest.fixture
def owner_cleanup(
    owner_engine: Engine, runtime_engine: Engine, provisioner_engine: Engine
) -> Iterator[OwnerCleanup]:
    """Owner-run cleanup; also fails the test if a role connection was left checked out."""
    cleanup = OwnerCleanup(owner_engine)
    yield cleanup
    failures = cleanup.run()
    leaked = {
        name: engine.pool.checkedout()
        for name, engine in (("runtime", runtime_engine), ("provisioner", provisioner_engine))
        if engine.pool.checkedout()
    }
    if failures or leaked:
        pytest.fail(f"Owner cleanup failures: {failures}; leaked connections: {leaked}")


# --- Transitional single-credential fixtures used by the existing suite ---------------------


@pytest.fixture(scope="session")
def db_engine(postgres_url: str, request: pytest.FixtureRequest):
    role_urls = _configured_role_urls()
    if role_urls is not None:
        if not same_database(postgres_url, role_urls[OWNER_ROLE]):
            pytest.fail("TEST_DATABASE_URL and the role URLs must target the same _test database.")
        # Owner migrations keep object ownership correct when both harnesses share the database.
        request.getfixturevalue("owner_engine")
    else:
        alembic_config = Config(str(ALEMBIC_INI))
        alembic_config.attributes["database_url"] = postgres_url
        command.upgrade(alembic_config, "head")
    engine = create_engine(postgres_url, pool_pre_ping=True)
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
