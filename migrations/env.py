# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

import logging
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, create_engine, pool

from app.config import get_settings
from app.persistence.database_roles import (
    BUSINESS_ROLES,
    MIGRATION_DATABASE_URL_VARIABLE,
    OWNER_ROLE,
    DatabaseRoleError,
    assert_connection_role,
)
from app.persistence.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata
logger = logging.getLogger("alembic.env")


def _database_url() -> tuple[str, bool]:
    """Return the migration URL and whether it is the dedicated owner credential."""
    explicit = config.attributes.get("database_url")
    if explicit:
        return explicit, False
    owner_url = os.environ.get(MIGRATION_DATABASE_URL_VARIABLE)
    if owner_url:
        return owner_url, True
    # Transitional single-credential installations (ADR 0029 §13 has not been performed).
    logger.warning(
        "%s is not set; migrating with the legacy application credential.",
        MIGRATION_DATABASE_URL_VARIABLE,
    )
    return get_settings().get_database_url(), False


def _verify_migration_role(connection: Connection, owner_required: bool) -> None:
    if owner_required or config.attributes.get("expected_role") == OWNER_ROLE:
        assert_connection_role(connection, OWNER_ROLE)
        return
    current = connection.exec_driver_sql("SELECT current_user").scalar_one()
    if current in BUSINESS_ROLES:
        raise DatabaseRoleError(f"Migrations must not run as {current!r}; use {OWNER_ROLE!r}.")


def run_migrations_offline() -> None:
    database_url, _ = _database_url()
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    external_connection = config.attributes.get("connection")
    if external_connection is not None:
        _verify_migration_role(external_connection, owner_required=False)
        context.configure(
            connection=external_connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
        return

    database_url, owner_required = _database_url()
    connectable = create_engine(database_url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        _verify_migration_role(connection, owner_required)
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
