# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

"""PostgreSQL role, ownership and privilege foundation (ADR 0029 §8, milestone 29.1a).

Two separate operator steps:

* ``bootstrap-roles`` is cluster-level. It requires a PostgreSQL superuser connection,
  creates or normalizes the three login roles, removes their role memberships and makes
  ``oscal_owner`` the owner of the database and its ``public`` schema. It never transfers
  ownership of existing application objects; that belongs to the coordinated installation
  (ADR 0029 §13).
* ``apply-privileges`` is database-level. It runs as ``oscal_owner`` after Alembic
  migrations, verifies ownership and the explicit table classification below, and
  re-establishes the database, schema, table, column, sequence, routine and default ACLs.

This module grants nothing to roles by default. A table that is not classified in
``RUNTIME_TABLE_ACCESS`` makes ``apply-privileges`` fail, so every new migration must
classify its objects explicitly.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from sqlalchemy import Connection, Engine, create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

logger = logging.getLogger(__name__)

OWNER_ROLE = "oscal_owner"
RUNTIME_ROLE = "oscal_runtime"
PROVISIONER_ROLE = "oscal_provisioner"
BUSINESS_ROLES = (RUNTIME_ROLE, PROVISIONER_ROLE)
ALL_ROLES = (OWNER_ROLE, RUNTIME_ROLE, PROVISIONER_ROLE)
TRUSTED_SCHEMA = "public"
MIGRATION_DATABASE_URL_VARIABLE = "MIGRATION_DATABASE_URL"
MINIMUM_PASSWORD_LENGTH = 16

TABLE_PRIVILEGE_NAMES = (
    "SELECT",
    "INSERT",
    "UPDATE",
    "DELETE",
    "TRUNCATE",
    "REFERENCES",
    "TRIGGER",
)


class DatabaseRoleError(RuntimeError):
    """Raised when a connection, role or privilege state violates the role contract."""


class TableClass(StrEnum):
    MIGRATION = "migration"
    ADMINISTRATIVE = "administrative"
    IDENTITY = "identity"
    SEED_MARKER = "seed_marker"
    WORKING = "working"
    IMMUTABLE = "immutable"


@dataclass(frozen=True)
class RuntimeTableAccess:
    """Explicit runtime privileges for one table.

    ``transitional_lock_columns`` receive UPDATE only because existing code or triggers take
    row locks (``FOR UPDATE``/``FOR SHARE``) on rows the runtime never updates. PostgreSQL
    requires UPDATE on at least one column for any row lock. Their removal is assigned to
    milestone 29.1b (installation gate replaces these locks, ADR 0029 §8 and §10).
    """

    classification: TableClass
    privileges: frozenset[str] = frozenset()
    insert_columns: tuple[str, ...] = ()
    update_columns: tuple[str, ...] = ()
    transitional_lock_columns: tuple[str, ...] = ()
    note: str = field(default="", compare=False)


_SELECT = frozenset({"SELECT"})
_APPEND = frozenset({"SELECT", "INSERT"})
_APPEND_DELETE = frozenset({"SELECT", "INSERT", "DELETE"})
_MUTABLE = frozenset({"SELECT", "INSERT", "UPDATE"})
_MUTABLE_DELETE = frozenset({"SELECT", "INSERT", "UPDATE", "DELETE"})

RUNTIME_TABLE_ACCESS: Mapping[str, RuntimeTableAccess] = {
    "alembic_version": RuntimeTableAccess(TableClass.MIGRATION, note="Owner-only migration state."),
    "tenants": RuntimeTableAccess(
        TableClass.ADMINISTRATIVE, _SELECT, note="Created by owner-run administrative bootstrap."
    ),
    "tenant_memberships": RuntimeTableAccess(
        TableClass.ADMINISTRATIVE, _SELECT, note="Membership administration is not a runtime write."
    ),
    "organizations": RuntimeTableAccess(
        TableClass.ADMINISTRATIVE, _SELECT, note="No supported runtime entry point creates them."
    ),
    "user_identities": RuntimeTableAccess(
        TableClass.IDENTITY,
        _SELECT,
        insert_columns=(
            "id",
            "issuer",
            "subject",
            "display_name",
            "email",
            "created_at",
            "updated_at",
        ),
        update_columns=("display_name", "email", "updated_at"),
        note="Identity upsert: keys on INSERT, display attributes on conflict UPDATE.",
    ),
    "demo_seed_runs": RuntimeTableAccess(TableClass.SEED_MARKER, _APPEND),
    "catalogs": RuntimeTableAccess(
        TableClass.WORKING,
        _APPEND,
        transitional_lock_columns=("updated_at",),
        note="Locked FOR UPDATE when allocating catalog revision numbers.",
    ),
    "catalog_revisions": RuntimeTableAccess(
        TableClass.WORKING,
        _APPEND,
        transitional_lock_columns=("updated_at",),
        note="Locked FOR UPDATE by services and by revision-lock triggers.",
    ),
    "catalog_group_indexes": RuntimeTableAccess(TableClass.WORKING, _APPEND),
    "catalog_control_indexes": RuntimeTableAccess(TableClass.WORKING, _APPEND),
    "profiles": RuntimeTableAccess(TableClass.WORKING, _MUTABLE),
    "profile_imports": RuntimeTableAccess(TableClass.WORKING, _MUTABLE),
    "mapping_collections": RuntimeTableAccess(TableClass.WORKING, _MUTABLE_DELETE),
    "mapping_members": RuntimeTableAccess(TableClass.WORKING, _APPEND_DELETE),
    "control_implementations": RuntimeTableAccess(TableClass.WORKING, _MUTABLE),
    "implementation_responsibilities": RuntimeTableAccess(TableClass.WORKING, _APPEND_DELETE),
    "component_definitions": RuntimeTableAccess(TableClass.WORKING, _MUTABLE_DELETE),
    "component_definition_components": RuntimeTableAccess(TableClass.WORKING, _APPEND_DELETE),
    "component_definition_sources": RuntimeTableAccess(TableClass.WORKING, _APPEND_DELETE),
    "component_definition_snapshots": RuntimeTableAccess(TableClass.IMMUTABLE, _APPEND),
    "information_systems": RuntimeTableAccess(TableClass.WORKING, _MUTABLE),
    "system_components": RuntimeTableAccess(TableClass.WORKING, _MUTABLE),
    "system_security_plans": RuntimeTableAccess(TableClass.WORKING, _MUTABLE),
    "system_security_plan_implementations": RuntimeTableAccess(
        TableClass.WORKING,
        _APPEND_DELETE,
        transitional_lock_columns=("created_at",),
        note="Associations are locked FOR UPDATE during SSP publication and removal.",
    ),
    "system_security_plan_versions": RuntimeTableAccess(TableClass.IMMUTABLE, _APPEND),
    "assessment_plans": RuntimeTableAccess(TableClass.WORKING, _MUTABLE),
    "assessment_plan_versions": RuntimeTableAccess(TableClass.IMMUTABLE, _APPEND),
    "assessment_results": RuntimeTableAccess(TableClass.WORKING, _MUTABLE),
    "assessment_result_versions": RuntimeTableAccess(TableClass.IMMUTABLE, _APPEND),
}

# Milestone 29.1a prepares only the isolated provisioner role and credential boundary.
# Grant issuance, revocation and assurance procedures (and their privileges) are later work.
PROVISIONER_TABLE_ACCESS: Mapping[str, RuntimeTableAccess] = {}


@dataclass(frozen=True)
class RolePasswords:
    owner: str = field(repr=False)
    runtime: str = field(repr=False)
    provisioner: str = field(repr=False)

    def __post_init__(self) -> None:
        values = (self.owner, self.runtime, self.provisioner)
        if any(len(value) < MINIMUM_PASSWORD_LENGTH for value in values):
            raise DatabaseRoleError(
                f"Each database role password must have at least "
                f"{MINIMUM_PASSWORD_LENGTH} characters."
            )
        if len(set(values)) != len(values):
            raise DatabaseRoleError("Database role passwords must be distinct.")

    def for_role(self, role: str) -> str:
        return {
            OWNER_ROLE: self.owner,
            RUNTIME_ROLE: self.runtime,
            PROVISIONER_ROLE: self.provisioner,
        }[role]


_ROLE_QUERY = (
    "SELECT current_user, session_user, rolsuper, rolinherit, rolcreaterole, rolcreatedb, "
    "rolreplication, rolbypassrls FROM pg_catalog.pg_roles WHERE rolname = current_user"
)


def _check_role_row(row: Any, expected_role: str) -> None:
    if row is None:
        raise DatabaseRoleError("Unable to determine the effective database role.")
    current, session, superuser, inherit, createrole, createdb, replication, bypassrls = row
    if current != expected_role or session != expected_role:
        raise DatabaseRoleError(
            f"Database connection uses role {session!r}/{current!r}; expected {expected_role!r}."
        )
    if superuser or createrole or replication or bypassrls:
        raise DatabaseRoleError(f"Role {expected_role!r} has forbidden cluster attributes.")
    if expected_role in BUSINESS_ROLES and (inherit or createdb):
        raise DatabaseRoleError(f"Role {expected_role!r} must be NOINHERIT and NOCREATEDB.")


def assert_connection_role(connection: Connection, expected_role: str) -> None:
    """Assert the effective and session role of an SQLAlchemy connection."""
    _check_role_row(connection.exec_driver_sql(_ROLE_QUERY).one(), expected_role)


def _assert_dbapi_role(dbapi_connection: Any, expected_role: str) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute(_ROLE_QUERY)
        row = cursor.fetchone()
    finally:
        cursor.close()
    dbapi_connection.rollback()
    _check_role_row(row, expected_role)


def create_role_engine(url: str, expected_role: str, **engine_options: Any) -> Engine:
    """Create an engine whose every new connection must authenticate as ``expected_role``.

    There is no fallback: a URL for another role is rejected before connecting, and a
    connection whose effective role differs is rejected when it is opened.
    """
    if expected_role not in ALL_ROLES:
        raise DatabaseRoleError(f"Unknown database role {expected_role!r}.")
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql":
        raise DatabaseRoleError("Database role engines require PostgreSQL.")
    if parsed.username != expected_role:
        raise DatabaseRoleError(
            f"Database URL for {expected_role!r} authenticates as {parsed.username!r}."
        )
    engine = create_engine(url, **engine_options)

    @event.listens_for(engine, "connect")
    def _verify_role(dbapi_connection: Any, _connection_record: Any) -> None:
        _assert_dbapi_role(dbapi_connection, expected_role)

    return engine


def _quote(connection: Connection, identifier: str) -> str:
    return connection.dialect.identifier_preparer.quote_identifier(identifier)


def bootstrap_roles(admin_url: str, passwords: RolePasswords) -> None:
    """Cluster-level bootstrap. Requires a superuser connection to the target database."""
    from psycopg import sql

    database = make_url(admin_url).database
    if not database:
        raise DatabaseRoleError("The administrative URL must name the target database.")
    engine = create_engine(admin_url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            current, superuser = connection.exec_driver_sql(
                "SELECT current_user, rolsuper FROM pg_catalog.pg_roles "
                "WHERE rolname = current_user"
            ).one()
            if not superuser or current in ALL_ROLES:
                raise DatabaseRoleError(
                    "Cluster role bootstrap requires a separate PostgreSQL superuser connection."
                )
            foreign_objects = connection.execute(
                text(
                    "SELECT count(*) FROM pg_catalog.pg_class c "
                    "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = :schema "
                    "AND pg_catalog.pg_get_userbyid(c.relowner) <> :owner"
                ),
                {"schema": TRUSTED_SCHEMA, "owner": OWNER_ROLE},
            ).scalar_one()
            if foreign_objects:
                raise DatabaseRoleError(
                    f"Schema {TRUSTED_SCHEMA!r} contains {foreign_objects} objects not owned by "
                    f"{OWNER_ROLE!r}. Ownership transfer is part of the coordinated installation "
                    "(ADR 0029 §13) and is not performed by this bootstrap."
                )
            raw = connection.connection.driver_connection
            for role in ALL_ROLES:
                exists = connection.execute(
                    text("SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = :role"),
                    {"role": role},
                ).scalar()
                statement = sql.SQL(
                    "{} ROLE {} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT "
                    "NOREPLICATION NOBYPASSRLS PASSWORD {}"
                ).format(
                    sql.SQL("ALTER" if exists else "CREATE"),
                    sql.Identifier(role),
                    sql.Literal(passwords.for_role(role)),
                )
                with raw.cursor() as cursor:
                    cursor.execute(statement)
            memberships = connection.execute(
                text(
                    "SELECT g.rolname, m.rolname, gr.rolname FROM pg_catalog.pg_auth_members a "
                    "JOIN pg_catalog.pg_roles g ON g.oid = a.roleid "
                    "JOIN pg_catalog.pg_roles m ON m.oid = a.member "
                    "JOIN pg_catalog.pg_roles gr ON gr.oid = a.grantor "
                    "WHERE m.rolname = ANY(:roles)"
                ),
                {"roles": list(ALL_ROLES)},
            ).all()
            for granted, member, grantor in memberships:
                connection.exec_driver_sql(
                    f"REVOKE {_quote(connection, granted)} FROM {_quote(connection, member)} "
                    f"GRANTED BY {_quote(connection, grantor)}"
                )
            connection.exec_driver_sql(
                f"ALTER DATABASE {_quote(connection, database)} OWNER TO {OWNER_ROLE}"
            )
            connection.exec_driver_sql(f"ALTER SCHEMA {TRUSTED_SCHEMA} OWNER TO {OWNER_ROLE}")
    finally:
        engine.dispose()
    logger.info("database_roles_bootstrapped database=%s", database)


def _ownership_violations(connection: Connection) -> list[str]:
    rows = connection.execute(
        text(
            "SELECT 'database ' || d.datname FROM pg_catalog.pg_database d "
            "WHERE d.datname = current_database() "
            "AND pg_catalog.pg_get_userbyid(d.datdba) <> :owner "
            "UNION ALL SELECT 'schema ' || n.nspname FROM pg_catalog.pg_namespace n "
            "WHERE n.nspname = :schema AND pg_catalog.pg_get_userbyid(n.nspowner) <> :owner "
            "UNION ALL SELECT 'relation ' || c.relname FROM pg_catalog.pg_class c "
            "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = :schema AND pg_catalog.pg_get_userbyid(c.relowner) <> :owner "
            "UNION ALL SELECT 'routine ' || p.proname FROM pg_catalog.pg_proc p "
            "JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = :schema AND pg_catalog.pg_get_userbyid(p.proowner) <> :owner "
            "UNION ALL SELECT 'type ' || t.typname FROM pg_catalog.pg_type t "
            "JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace "
            "WHERE n.nspname = :schema AND pg_catalog.pg_get_userbyid(t.typowner) <> :owner"
        ),
        {"schema": TRUSTED_SCHEMA, "owner": OWNER_ROLE},
    ).scalars()
    return sorted(rows)


def _schema_objects(connection: Connection) -> tuple[set[str], list[str]]:
    rows = connection.execute(
        text(
            "SELECT c.relname, c.relkind FROM pg_catalog.pg_class c "
            "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = :schema AND c.relkind NOT IN ('i', 'I', 't', 'c')"
        ),
        {"schema": TRUSTED_SCHEMA},
    ).all()
    tables = {name for name, kind in rows if kind in ("r", "p")}
    unsupported = sorted(f"{name} ({kind})" for name, kind in rows if kind not in ("r", "p"))
    return tables, unsupported


def apply_privileges(connection: Connection) -> None:
    """Re-establish all ACLs. Run as ``oscal_owner`` inside one transaction."""
    assert_connection_role(connection, OWNER_ROLE)
    existing_roles = set(
        connection.execute(
            text("SELECT rolname FROM pg_catalog.pg_roles WHERE rolname = ANY(:roles)"),
            {"roles": list(ALL_ROLES)},
        ).scalars()
    )
    if existing_roles != set(ALL_ROLES):
        raise DatabaseRoleError("Bootstrap the database roles before applying privileges.")
    violations = _ownership_violations(connection)
    if violations:
        raise DatabaseRoleError(f"Objects not owned by {OWNER_ROLE!r}: {', '.join(violations)}.")
    tables, unsupported = _schema_objects(connection)
    if unsupported:
        raise DatabaseRoleError(
            f"Unclassified non-table objects in {TRUSTED_SCHEMA!r}: {', '.join(unsupported)}."
        )
    unclassified = sorted(tables - set(RUNTIME_TABLE_ACCESS))
    missing = sorted(set(RUNTIME_TABLE_ACCESS) - tables)
    if unclassified or missing:
        raise DatabaseRoleError(
            f"Table privilege classification mismatch; unclassified={unclassified}, "
            f"missing={missing}."
        )

    database = _quote(
        connection, connection.exec_driver_sql("SELECT current_database()").scalar_one()
    )
    business = ", ".join(BUSINESS_ROLES)
    revokees = f"PUBLIC, {business}"
    statements = [
        f"REVOKE ALL ON DATABASE {database} FROM {revokees}",
        f"GRANT CONNECT ON DATABASE {database} TO {business}",
        f"REVOKE ALL ON SCHEMA {TRUSTED_SCHEMA} FROM {revokees}",
        f"GRANT USAGE ON SCHEMA {TRUSTED_SCHEMA} TO {business}",
        f"REVOKE ALL ON ALL TABLES IN SCHEMA {TRUSTED_SCHEMA} FROM {revokees}",
        f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA {TRUSTED_SCHEMA} FROM {revokees}",
        f"REVOKE ALL ON ALL ROUTINES IN SCHEMA {TRUSTED_SCHEMA} FROM {revokees}",
        f"ALTER DEFAULT PRIVILEGES FOR ROLE {OWNER_ROLE} REVOKE EXECUTE ON ROUTINES FROM PUBLIC",
        f"ALTER DEFAULT PRIVILEGES FOR ROLE {OWNER_ROLE} IN SCHEMA {TRUSTED_SCHEMA} "
        f"REVOKE ALL ON TABLES FROM {business}",
        f"ALTER DEFAULT PRIVILEGES FOR ROLE {OWNER_ROLE} IN SCHEMA {TRUSTED_SCHEMA} "
        f"REVOKE ALL ON SEQUENCES FROM {business}",
        f"ALTER DEFAULT PRIVILEGES FOR ROLE {OWNER_ROLE} IN SCHEMA {TRUSTED_SCHEMA} "
        f"REVOKE ALL ON ROUTINES FROM {business}",
    ]
    for table in sorted(tables):
        columns = connection.execute(
            text(
                "SELECT a.attname FROM pg_catalog.pg_attribute a "
                "JOIN pg_catalog.pg_class c ON c.oid = a.attrelid "
                "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = :schema AND c.relname = :table "
                "AND a.attnum > 0 AND NOT a.attisdropped ORDER BY a.attnum"
            ),
            {"schema": TRUSTED_SCHEMA, "table": table},
        ).scalars()
        column_list = ", ".join(_quote(connection, column) for column in columns)
        statements.append(
            f"REVOKE ALL ({column_list}) ON {TRUSTED_SCHEMA}.{_quote(connection, table)} "
            f"FROM {revokees}"
        )
    for role, manifest in (
        (RUNTIME_ROLE, RUNTIME_TABLE_ACCESS),
        (PROVISIONER_ROLE, PROVISIONER_TABLE_ACCESS),
    ):
        for table, access in sorted(manifest.items()):
            target = f"{TRUSTED_SCHEMA}.{_quote(connection, table)}"
            if access.privileges:
                statements.append(
                    f"GRANT {', '.join(sorted(access.privileges))} ON {target} TO {role}"
                )
            if access.insert_columns:
                cols = ", ".join(_quote(connection, column) for column in access.insert_columns)
                statements.append(f"GRANT INSERT ({cols}) ON {target} TO {role}")
            update_columns = access.update_columns + access.transitional_lock_columns
            if update_columns:
                cols = ", ".join(_quote(connection, column) for column in update_columns)
                statements.append(f"GRANT UPDATE ({cols}) ON {target} TO {role}")
    for statement in statements:
        connection.exec_driver_sql(statement)
    logger.info("database_privileges_applied tables=%s", len(tables))


def _required_environment(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise DatabaseRoleError(f"Set {name}.")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.persistence.database_roles")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "bootstrap-roles",
        help="Cluster-level: create/normalize roles (DATABASE_ADMIN_URL, OSCAL_*_DB_PASSWORD).",
    )
    commands.add_parser(
        "apply-privileges",
        help=f"Database-level: apply ACLs as {OWNER_ROLE} ({MIGRATION_DATABASE_URL_VARIABLE}).",
    )
    arguments = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    try:
        if arguments.command == "bootstrap-roles":
            bootstrap_roles(
                _required_environment("DATABASE_ADMIN_URL"),
                RolePasswords(
                    owner=_required_environment("OSCAL_OWNER_DB_PASSWORD"),
                    runtime=_required_environment("OSCAL_RUNTIME_DB_PASSWORD"),
                    provisioner=_required_environment("OSCAL_PROVISIONER_DB_PASSWORD"),
                ),
            )
        else:
            engine = create_role_engine(
                _required_environment(MIGRATION_DATABASE_URL_VARIABLE),
                OWNER_ROLE,
                poolclass=NullPool,
            )
            try:
                with engine.begin() as connection:
                    apply_privileges(connection)
            finally:
                engine.dispose()
    except DatabaseRoleError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
