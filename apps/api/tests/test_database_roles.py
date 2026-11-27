# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

"""Executable evidence for the 29.1a PostgreSQL role foundation (ADR 0029 §8).

All assertions inspect effective privileges on real PostgreSQL connections that
authenticate with separate credentials. Nothing here uses the transitional
``TEST_DATABASE_URL`` fixtures.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.pool import NullPool

from app.persistence.database_roles import (
    ALL_ROLES,
    BUSINESS_ROLES,
    OWNER_ROLE,
    PROVISIONER_ROLE,
    PROVISIONER_TABLE_ACCESS,
    RUNTIME_ROLE,
    RUNTIME_TABLE_ACCESS,
    TABLE_PRIVILEGE_NAMES,
    DatabaseRoleError,
    _assert_dbapi_role,
    apply_privileges,
)
from tests.database_role_harness import OwnerCleanup, run_synchronized

pytestmark = [pytest.mark.integration, pytest.mark.database_roles]

INSUFFICIENT_PRIVILEGE = "42501"
PROTECTED_TRIGGERS = {
    "system_security_plan_versions": "trg_system_security_plan_version_immutable",
    "assessment_plan_versions": "trg_assessment_plan_version_immutable",
    "assessment_result_versions": "trg_assessment_result_version_immutable",
    "component_definition_snapshots": "trg_component_definition_snapshot_immutable",
    "catalog_revisions": "trg_published_catalog_revision_immutable",
}


def _engine_for(role: str, runtime_engine: Engine, provisioner_engine: Engine) -> Engine:
    return runtime_engine if role == RUNTIME_ROLE else provisioner_engine


def _assert_denied(engine: Engine, statement: str, sqlstate: str = INSUFFICIENT_PRIVILEGE) -> None:
    with engine.connect() as connection:
        with pytest.raises(DBAPIError) as raised:
            with connection.begin():
                connection.exec_driver_sql(statement)
        assert raised.value.orig is not None
        assert raised.value.orig.sqlstate == sqlstate, (statement, str(raised.value.orig))


def _tables(connection) -> list[str]:
    return list(
        connection.execute(
            text(
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') ORDER BY 1"
            )
        ).scalars()
    )


def _columns(connection, table: str) -> list[str]:
    return list(
        connection.execute(
            text(
                "SELECT attname FROM pg_attribute WHERE attrelid = to_regclass(:table) "
                "AND attnum > 0 AND NOT attisdropped"
            ),
            {"table": f"public.{table}"},
        ).scalars()
    )


# --- Effective roles and credentials ---------------------------------------------------------


@pytest.mark.parametrize("role", ALL_ROLES)
def test_each_connection_authenticates_as_its_own_restricted_role(
    role: str, owner_engine: Engine, runtime_engine: Engine, provisioner_engine: Engine
) -> None:
    engine = {
        OWNER_ROLE: owner_engine,
        RUNTIME_ROLE: runtime_engine,
        PROVISIONER_ROLE: provisioner_engine,
    }[role]
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT current_user, session_user, rolsuper, rolinherit, rolcreaterole, "
                "rolcreatedb, rolreplication, rolbypassrls, rolcanlogin, current_database() "
                "FROM pg_roles WHERE rolname = current_user"
            )
        ).one()
    assert row[0] == role and row[1] == role
    assert row[2:9] == (False, False, False, False, False, False, True)
    assert row[9].endswith("_test")


def test_connect_time_role_check_rejects_owner_session_for_runtime(owner_engine: Engine) -> None:
    # create_role_engine runs this check on every new DBAPI connection.
    raw = owner_engine.raw_connection()
    try:
        with pytest.raises(DatabaseRoleError, match="expected 'oscal_runtime'"):
            _assert_dbapi_role(raw.driver_connection, RUNTIME_ROLE)
    finally:
        raw.close()


@pytest.mark.parametrize(
    ("login_role", "password_of"),
    [
        (OWNER_ROLE, RUNTIME_ROLE),
        (OWNER_ROLE, PROVISIONER_ROLE),
        (RUNTIME_ROLE, PROVISIONER_ROLE),
        (PROVISIONER_ROLE, RUNTIME_ROLE),
    ],
)
def test_credentials_are_not_interchangeable(
    database_role_urls: dict[str, str], owner_engine: Engine, login_role: str, password_of: str
) -> None:
    url = make_url(database_role_urls[login_role]).set(
        password=make_url(database_role_urls[password_of]).password
    )
    engine = create_engine(url, poolclass=NullPool)
    try:
        with pytest.raises(OperationalError, match="password authentication failed"):
            with engine.connect():
                pass
    finally:
        engine.dispose()


@pytest.mark.parametrize("role", BUSINESS_ROLES)
def test_business_roles_hold_no_role_memberships(role: str, owner_engine: Engine) -> None:
    with owner_engine.connect() as connection:
        memberships = connection.execute(
            text(
                "SELECT g.rolname FROM pg_auth_members a JOIN pg_roles g ON g.oid = a.roleid "
                "JOIN pg_roles m ON m.oid = a.member WHERE m.rolname = :role"
            ),
            {"role": role},
        ).all()
        assumable = (
            connection.execute(
                text(
                    "SELECT rolname FROM pg_roles WHERE rolname <> :role "
                    "AND (pg_has_role(:role, oid, 'MEMBER') OR pg_has_role(:role, oid, 'USAGE') "
                    "OR pg_has_role(:role, oid, 'SET'))"
                ),
                {"role": role},
            )
            .scalars()
            .all()
        )
    assert memberships == []
    assert assumable == []


# --- Ownership -------------------------------------------------------------------------------


def test_database_schema_and_migrated_objects_are_owned_by_owner(owner_engine: Engine) -> None:
    with owner_engine.connect() as connection:
        database_owner = connection.execute(
            text(
                "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = current_database()"
            )
        ).scalar_one()
        schema_owner = connection.execute(
            text("SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname = 'public'")
        ).scalar_one()
        object_owners = set(
            connection.execute(
                text(
                    "SELECT pg_get_userbyid(c.relowner) FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' "
                    "UNION SELECT pg_get_userbyid(p.proowner) FROM pg_proc p "
                    "JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = 'public'"
                )
            ).scalars()
        )
        tables = _tables(connection)
        head = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert (database_owner, schema_owner, object_owners) == (OWNER_ROLE, OWNER_ROLE, {OWNER_ROLE})
    assert set(tables) == set(RUNTIME_TABLE_ACCESS)
    assert head == "c1a5f9e8d2b4"


def test_objects_created_by_later_migrations_are_owner_owned_and_denied_by_default(
    owner_engine: Engine,
) -> None:
    with owner_engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.exec_driver_sql("CREATE TABLE public.zz_future_table (id integer)")
            connection.exec_driver_sql("CREATE SEQUENCE public.zz_future_sequence")
            connection.exec_driver_sql(
                "CREATE FUNCTION public.zz_future_function() RETURNS integer "
                "LANGUAGE sql AS 'SELECT 1'"
            )
            owners = set(
                connection.execute(
                    text(
                        "SELECT pg_get_userbyid(relowner) FROM pg_class WHERE relname IN "
                        "('zz_future_table', 'zz_future_sequence') UNION SELECT "
                        "pg_get_userbyid(proowner) FROM pg_proc "
                        "WHERE proname = 'zz_future_function'"
                    )
                ).scalars()
            )
            assert owners == {OWNER_ROLE}
            for role in (*BUSINESS_ROLES, "public"):
                assert not connection.execute(
                    text(
                        "SELECT has_function_privilege(:role, "
                        "'public.zz_future_function()', 'EXECUTE')"
                    ),
                    {"role": role},
                ).scalar_one()
            for role in BUSINESS_ROLES:
                granted = connection.execute(
                    text(
                        "SELECT has_any_column_privilege(:role, 'public.zz_future_table', "
                        "'SELECT, INSERT, UPDATE, REFERENCES') OR has_table_privilege(:role, "
                        "'public.zz_future_table', 'DELETE, TRUNCATE, TRIGGER') OR "
                        "has_sequence_privilege(:role, 'public.zz_future_sequence', "
                        "'USAGE, SELECT, UPDATE')"
                    ),
                    {"role": role},
                ).scalar_one()
                assert granted is False
            with pytest.raises(DatabaseRoleError, match="zz_future"):
                with connection.begin_nested():
                    apply_privileges(connection)
        finally:
            transaction.rollback()


# --- Effective privileges --------------------------------------------------------------------


@pytest.mark.parametrize("role", BUSINESS_ROLES)
def test_effective_table_and_column_privileges_match_contract(
    role: str, owner_engine: Engine
) -> None:
    manifest = RUNTIME_TABLE_ACCESS if role == RUNTIME_ROLE else PROVISIONER_TABLE_ACCESS
    mismatches: list[str] = []
    with owner_engine.connect() as connection:
        for table in _tables(connection):
            access = manifest.get(table)
            granted = access.privileges if access else frozenset()
            for privilege in TABLE_PRIVILEGE_NAMES:
                actual = connection.execute(
                    text("SELECT has_table_privilege(:role, :table, :privilege)"),
                    {"role": role, "table": f"public.{table}", "privilege": privilege},
                ).scalar_one()
                if actual != (privilege in granted):
                    mismatches.append(f"{table}.{privilege}={actual}")
                if connection.execute(
                    text("SELECT has_table_privilege(:role, :table, :privilege)"),
                    {
                        "role": role,
                        "table": f"public.{table}",
                        "privilege": f"{privilege} WITH GRANT OPTION",
                    },
                ).scalar_one():
                    mismatches.append(f"{table}.{privilege} grant option")
            for column in _columns(connection, table):
                expected = {
                    "SELECT": "SELECT" in granted,
                    "INSERT": "INSERT" in granted
                    or bool(access and column in access.insert_columns),
                    "UPDATE": "UPDATE" in granted
                    or bool(
                        access
                        and column in access.update_columns + access.transitional_lock_columns
                    ),
                    "REFERENCES": False,
                }
                for privilege, wanted in expected.items():
                    actual = connection.execute(
                        text("SELECT has_column_privilege(:role, :table, :column, :privilege)"),
                        {
                            "role": role,
                            "table": f"public.{table}",
                            "column": column,
                            "privilege": privilege,
                        },
                    ).scalar_one()
                    if actual != wanted:
                        mismatches.append(f"{table}.{column}.{privilege}={actual}")
    assert mismatches == []


def test_database_schema_routine_and_default_acls_exclude_public(owner_engine: Engine) -> None:
    with owner_engine.connect() as connection:
        database = connection.execute(text("SELECT current_database()")).scalar_one()
        result = {}
        for role in ("public", *BUSINESS_ROLES):
            result[role] = connection.execute(
                text(
                    "SELECT has_database_privilege(:role, :db, 'CONNECT'), "
                    "has_database_privilege(:role, :db, 'TEMPORARY'), "
                    "has_database_privilege(:role, :db, 'CREATE'), "
                    "has_schema_privilege(:role, 'public', 'USAGE'), "
                    "has_schema_privilege(:role, 'public', 'CREATE')"
                ),
                {"role": role, "db": database},
            ).one()
        executable = connection.execute(
            text(
                "SELECT p.proname, r.rolname FROM pg_proc p "
                "JOIN pg_namespace n ON n.oid = p.pronamespace "
                "CROSS JOIN (SELECT unnest(ARRAY['public', :runtime, :provisioner]) rolname) r "
                "WHERE n.nspname = 'public' "
                "AND has_function_privilege(r.rolname, p.oid, 'EXECUTE')"
            ),
            {"runtime": RUNTIME_ROLE, "provisioner": PROVISIONER_ROLE},
        ).all()
        unsafe_definers = (
            connection.execute(
                text(
                    "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
                    "WHERE n.nspname = 'public' AND p.prosecdef AND NOT EXISTS ("
                    "SELECT 1 FROM unnest(coalesce(p.proconfig, '{}')) c "
                    "WHERE c LIKE 'search_path=%' AND c LIKE '%pg_temp')"
                )
            )
            .scalars()
            .all()
        )
        default_function_acl = connection.execute(
            text(
                "SELECT d.defaclacl::text FROM pg_default_acl d "
                "WHERE d.defaclrole = to_regrole(:owner) AND d.defaclnamespace = 0 "
                "AND d.defaclobjtype = 'f'"
            ),
            {"owner": OWNER_ROLE},
        ).scalar_one()
    assert result["public"] == (False, False, False, False, False)
    for role in BUSINESS_ROLES:
        assert result[role] == (True, False, False, True, False)
    assert executable == []
    assert unsafe_definers == []
    entries = default_function_acl.strip("{}").split(",")
    assert entries == [f"{OWNER_ROLE}=X/{OWNER_ROLE}"]  # no EXECUTE for PUBLIC on new routines


def test_runtime_trigger_functions_are_not_directly_executable(runtime_engine: Engine) -> None:
    _assert_denied(runtime_engine, "SELECT public.protect_ssp_immutable_records()")


def test_no_sequences_exist_so_no_sequence_privileges_are_required(owner_engine: Engine) -> None:
    with owner_engine.connect() as connection:
        sequences = connection.execute(
            text(
                "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relkind = 'S'"
            )
        ).scalar_one()
    assert sequences == 0


def test_apply_privileges_is_idempotent_and_refuses_non_owner(
    owner_engine: Engine, runtime_engine: Engine
) -> None:
    with owner_engine.begin() as connection:
        apply_privileges(connection)
    with runtime_engine.connect() as connection:
        with pytest.raises(DatabaseRoleError, match="expected 'oscal_owner'"):
            apply_privileges(connection)
        connection.rollback()


# --- Negative statements on real connections -------------------------------------------------

ESCALATION_STATEMENTS = [
    "SET ROLE oscal_owner",
    "SET SESSION AUTHORIZATION oscal_owner",
    "CREATE TABLE public.zz_probe (id integer)",
    "CREATE TEMPORARY TABLE zz_temp_probe (id integer)",
    "CREATE SCHEMA zz_probe_schema",
    "CREATE FUNCTION public.zz_probe() RETURNS integer LANGUAGE sql AS 'SELECT 1'",
    "CREATE OR REPLACE FUNCTION public.protect_ssp_immutable_records() RETURNS trigger "
    "LANGUAGE plpgsql AS $$BEGIN RETURN NEW; END$$",
    "ALTER FUNCTION public.protect_ssp_immutable_records() OWNER TO CURRENT_USER",
    "DROP FUNCTION public.prevent_published_catalog_revision_mutation() CASCADE",
    "ALTER TABLE public.tenants OWNER TO CURRENT_USER",
    "ALTER TABLE public.system_security_plan_versions DISABLE TRIGGER ALL",
    "ALTER TABLE public.assessment_plan_versions "
    "DISABLE TRIGGER trg_assessment_plan_version_immutable",
    "DROP TRIGGER trg_assessment_result_version_immutable ON public.assessment_result_versions",
    "SET session_replication_role = replica",
    "CREATE ROLE zz_probe_role",
    "GRANT oscal_owner TO CURRENT_USER",
    "ALTER ROLE oscal_owner PASSWORD 'zz-not-allowed-123'",
    "ALTER DEFAULT PRIVILEGES FOR ROLE oscal_owner GRANT ALL ON TABLES TO CURRENT_USER",
]


@pytest.mark.parametrize("role", BUSINESS_ROLES)
@pytest.mark.parametrize("statement", ESCALATION_STATEMENTS)
def test_business_roles_cannot_escalate_or_alter_protected_objects(
    role: str, statement: str, runtime_engine: Engine, provisioner_engine: Engine
) -> None:
    _assert_denied(_engine_for(role, runtime_engine, provisioner_engine), statement)


@pytest.mark.parametrize("role", BUSINESS_ROLES)
def test_business_roles_cannot_assume_each_other(
    role: str, runtime_engine: Engine, provisioner_engine: Engine
) -> None:
    other = PROVISIONER_ROLE if role == RUNTIME_ROLE else RUNTIME_ROLE
    _assert_denied(_engine_for(role, runtime_engine, provisioner_engine), f"SET ROLE {other}")


@pytest.mark.parametrize("role", BUSINESS_ROLES)
@pytest.mark.parametrize("table", sorted(RUNTIME_TABLE_ACCESS))
def test_business_roles_cannot_truncate_any_table(
    role: str, table: str, runtime_engine: Engine, provisioner_engine: Engine
) -> None:
    _assert_denied(
        _engine_for(role, runtime_engine, provisioner_engine), f"TRUNCATE public.{table}"
    )


RUNTIME_FORBIDDEN_DML = [
    "INSERT INTO public.tenants (id, name, slug, created_at, updated_at) "
    "VALUES (gen_random_uuid(), 'x', 'x', now(), now())",
    "UPDATE public.tenants SET name = name",
    "DELETE FROM public.tenants",
    "INSERT INTO public.tenant_memberships (id, tenant_id, user_id, role, status, created_at, "
    "updated_at) VALUES (gen_random_uuid(), gen_random_uuid(), gen_random_uuid(), "
    "'tenant_admin', 'active', now(), now())",
    "UPDATE public.tenant_memberships SET role = 'tenant_admin'",
    "DELETE FROM public.tenant_memberships",
    "INSERT INTO public.organizations (id, tenant_id, name, slug, created_at, updated_at) "
    "VALUES (gen_random_uuid(), gen_random_uuid(), 'x', 'x', now(), now())",
    "UPDATE public.user_identities SET issuer = issuer",
    "UPDATE public.user_identities SET subject = subject",
    "DELETE FROM public.user_identities",
    "SELECT * FROM public.alembic_version",
    "UPDATE public.alembic_version SET version_num = version_num",
    "UPDATE public.system_security_plan_versions SET id = id",
    "DELETE FROM public.system_security_plan_versions",
    "UPDATE public.assessment_plan_versions SET id = id",
    "DELETE FROM public.assessment_plan_versions",
    "UPDATE public.assessment_result_versions SET id = id",
    "DELETE FROM public.assessment_result_versions",
    "UPDATE public.component_definition_snapshots SET id = id",
    "DELETE FROM public.component_definition_snapshots",
    "UPDATE public.catalog_revisions SET content = content",
    "DELETE FROM public.catalog_revisions",
    "DELETE FROM public.catalogs",
    "UPDATE public.demo_seed_runs SET seed_name = seed_name",
    "DELETE FROM public.demo_seed_runs",
]


@pytest.mark.parametrize("statement", RUNTIME_FORBIDDEN_DML)
def test_runtime_cannot_perform_unauthorized_dml(statement: str, runtime_engine: Engine) -> None:
    _assert_denied(runtime_engine, statement)


@pytest.mark.parametrize("table", sorted(RUNTIME_TABLE_ACCESS))
def test_provisioner_cannot_read_or_write_business_tables(
    table: str, provisioner_engine: Engine
) -> None:
    _assert_denied(provisioner_engine, f"SELECT 1 FROM public.{table} LIMIT 1")
    _assert_denied(provisioner_engine, f"DELETE FROM public.{table}")


def test_runtime_grant_attempt_does_not_create_privileges(
    runtime_engine: Engine, owner_engine: Engine
) -> None:
    with runtime_engine.begin() as connection:
        # PostgreSQL reports a WARNING, not an error, when no grantable privilege exists.
        connection.exec_driver_sql("GRANT SELECT ON public.tenants TO oscal_provisioner")
    with owner_engine.connect() as connection:
        assert not connection.execute(
            text("SELECT has_table_privilege('oscal_provisioner', 'public.tenants', 'SELECT')")
        ).scalar_one()


# --- Positive runtime operations at SQL level -------------------------------------------------


def _owner_tenant(owner_cleanup: OwnerCleanup, *, removable: bool = True) -> str:
    tenant_id = str(uuid4())
    now = datetime.now(UTC)
    with owner_cleanup.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO tenants (id, name, slug, created_at, updated_at) "
                "VALUES (:id, 'Role harness', :slug, :now, :now)"
            ),
            {"id": tenant_id, "slug": f"role-{tenant_id}", "now": now},
        )
    if removable:
        owner_cleanup.add(
            "delete role-harness tenant",
            lambda connection: connection.execute(
                text("DELETE FROM tenants WHERE id = :id"), {"id": tenant_id}
            ),
        )
    return tenant_id


def test_runtime_insert_returning_fk_validation_and_owner_cleanup(
    runtime_engine: Engine, owner_cleanup: OwnerCleanup
) -> None:
    tenant_id = _owner_tenant(owner_cleanup)
    owner_cleanup.add(
        "delete runtime seed marker",
        lambda connection: connection.execute(
            text("DELETE FROM demo_seed_runs WHERE tenant_id = :id"), {"id": tenant_id}
        ),
    )
    with runtime_engine.begin() as connection:
        applied_at = connection.execute(
            text(
                "INSERT INTO demo_seed_runs (tenant_id, seed_name) VALUES (:id, 'role-harness') "
                "RETURNING applied_at"
            ),
            {"id": tenant_id},
        ).scalar_one()
    assert applied_at is not None
    _assert_denied(
        runtime_engine,
        f"INSERT INTO demo_seed_runs (tenant_id, seed_name) VALUES ('{uuid4()}', 'missing')",
        sqlstate="23503",
    )


def test_owner_cleanup_runs_every_action_and_reports_failures(owner_engine: Engine) -> None:
    executed: list[str] = []
    cleanup = OwnerCleanup(owner_engine)
    cleanup.add("first", lambda connection: executed.append("first"))
    cleanup.add("failing", lambda connection: connection.exec_driver_sql("SELECT 1/0"))
    cleanup.add(
        "role",
        lambda connection: executed.append(
            connection.exec_driver_sql("SELECT current_user").scalar_one()
        ),
    )
    failures = cleanup.run()
    assert executed == [OWNER_ROLE, "first"]
    assert len(failures) == 1 and failures[0].startswith("failing: ")
    assert cleanup.run() == []


def test_protected_trigger_still_fires_for_runtime_lock_column(
    runtime_engine: Engine, owner_cleanup: OwnerCleanup
) -> None:
    # A published revision is an immutable record and cannot be removed without bypassing
    # its trigger; the tenant therefore stays in the disposable test database.
    tenant_id = _owner_tenant(owner_cleanup, removable=False)
    catalog_id, revision_id = str(uuid4()), str(uuid4())
    now = datetime.now(UTC)
    with runtime_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO catalogs (id, tenant_id, name, origin_type, created_at, updated_at) "
                "VALUES (:id, :tenant, 'Role catalog', 'custom', :now, :now)"
            ),
            {"id": catalog_id, "tenant": tenant_id, "now": now},
        )
        connection.execute(
            text(
                "INSERT INTO catalog_revisions (id, tenant_id, catalog_id, revision_number, "
                "lifecycle_status, oscal_document_uuid, oscal_version, content_sha256, content, "
                "created_at, updated_at) VALUES (:id, :tenant, :catalog, 1, 'draft', :doc, "
                "'1.2.1', :digest, '{}'::jsonb, :now, :now)"
            ),
            {
                "id": revision_id,
                "tenant": tenant_id,
                "catalog": catalog_id,
                "doc": str(uuid4()),
                "digest": "0" * 64,
                "now": now,
            },
        )
        locked = connection.execute(
            text("SELECT id FROM catalog_revisions WHERE id = :id FOR UPDATE"), {"id": revision_id}
        ).scalar_one()
    assert str(locked) == revision_id
    with owner_cleanup.engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE catalog_revisions SET lifecycle_status = 'published', published_at = now() "
                "WHERE id = :id"
            ),
            {"id": revision_id},
        )
    # Published revisions are immutable records; they remain in the disposable test database.
    _assert_denied(
        runtime_engine,
        f"UPDATE catalog_revisions SET updated_at = now() WHERE id = '{revision_id}'",
        sqlstate="23514",
    )


# --- Independent sessions and synchronization -----------------------------------------------


def test_independent_business_sessions_synchronize_with_bounded_waits(
    runtime_engine: Engine, provisioner_engine: Engine
) -> None:
    key = int(uuid4().int % (2**62))
    holder_ready = threading.Event()

    def holder(barrier: threading.Barrier) -> str:
        with runtime_engine.connect() as connection:
            with connection.begin():
                connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
                holder_ready.set()
                barrier.wait()  # contender has observed the held lock
            return connection.execute(text("SELECT current_user")).scalar_one()

    def contender(barrier: threading.Barrier) -> tuple[str, str]:
        assert holder_ready.wait(timeout=10)
        with provisioner_engine.connect() as connection:
            with pytest.raises(OperationalError) as raised:
                with connection.begin():
                    connection.exec_driver_sql("SET LOCAL lock_timeout = '200ms'")
                    connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
            first = raised.value.orig.sqlstate
            barrier.wait()
            with connection.begin():
                connection.exec_driver_sql("SET LOCAL lock_timeout = '5s'")
                connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
                second = connection.execute(text("SELECT current_user")).scalar_one()
            return first, second

    holder_role, (timeout_state, contender_role) = run_synchronized(holder, contender)
    assert holder_role == RUNTIME_ROLE
    assert timeout_state == "55P03"  # lock_not_available
    assert contender_role == PROVISIONER_ROLE
