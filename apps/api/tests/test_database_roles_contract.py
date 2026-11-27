# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

"""Database-independent checks of the explicit runtime privilege classification."""

import pytest

from app.persistence.database_roles import (
    PROVISIONER_TABLE_ACCESS,
    RUNTIME_TABLE_ACCESS,
    DatabaseRoleError,
    RolePasswords,
    TableClass,
    create_role_engine,
)
from app.persistence.models import Base
from tests.database_role_harness import (
    ROLE_URL_VARIABLES,
    RoleHarnessConfigurationError,
    load_role_urls,
)

VERSION_TABLES = {
    "system_security_plan_versions",
    "assessment_plan_versions",
    "assessment_result_versions",
    "component_definition_snapshots",
}


def test_every_mapped_table_and_migration_table_is_classified_exactly() -> None:
    assert set(RUNTIME_TABLE_ACCESS) == set(Base.metadata.tables) | {"alembic_version"}


def test_classified_columns_exist() -> None:
    for name, access in RUNTIME_TABLE_ACCESS.items():
        if name == "alembic_version":
            continue
        columns = set(Base.metadata.tables[name].columns.keys())
        referenced = (
            set(access.insert_columns)
            | set(access.update_columns)
            | set(access.transitional_lock_columns)
        )
        assert referenced <= columns, name


def test_no_dangerous_or_unknown_privileges_are_granted() -> None:
    for access in RUNTIME_TABLE_ACCESS.values():
        assert access.privileges <= {"SELECT", "INSERT", "UPDATE", "DELETE"}


def test_immutable_and_administrative_tables_are_not_mutable_by_runtime() -> None:
    for name in VERSION_TABLES:
        access = RUNTIME_TABLE_ACCESS[name]
        assert access.classification is TableClass.IMMUTABLE
        assert access.privileges == {"SELECT", "INSERT"}
        assert not access.update_columns and not access.transitional_lock_columns
    for name in ("tenants", "tenant_memberships", "organizations"):
        access = RUNTIME_TABLE_ACCESS[name]
        assert access.privileges == {"SELECT"}
        assert not (access.insert_columns or access.update_columns)
    assert RUNTIME_TABLE_ACCESS["alembic_version"].privileges == frozenset()


def test_identity_keys_are_insert_only_for_runtime() -> None:
    access = RUNTIME_TABLE_ACCESS["user_identities"]
    assert access.privileges == {"SELECT"}
    assert {"issuer", "subject", "id"} <= set(access.insert_columns)
    assert set(access.update_columns) == {"display_name", "email", "updated_at"}


def test_transitional_lock_privileges_are_limited_and_documented() -> None:
    transitional = {
        name: access.transitional_lock_columns
        for name, access in RUNTIME_TABLE_ACCESS.items()
        if access.transitional_lock_columns
    }
    assert transitional == {
        "catalogs": ("updated_at",),
        "catalog_revisions": ("updated_at",),
        "system_security_plan_implementations": ("created_at",),
    }
    assert all(RUNTIME_TABLE_ACCESS[name].note for name in transitional)


def test_provisioner_has_no_business_privileges_in_this_milestone() -> None:
    assert PROVISIONER_TABLE_ACCESS == {}


def test_role_engine_rejects_url_for_another_role_without_connecting() -> None:
    with pytest.raises(DatabaseRoleError, match="authenticates as 'oscal_owner'"):
        create_role_engine(
            "postgresql+psycopg://oscal_owner:x@127.0.0.1:1/example_test", "oscal_runtime"
        )
    with pytest.raises(DatabaseRoleError, match="Unknown database role"):
        create_role_engine("postgresql+psycopg://postgres:x@127.0.0.1:1/example_test", "postgres")


def test_role_passwords_must_be_distinct_and_long() -> None:
    with pytest.raises(DatabaseRoleError, match="distinct"):
        RolePasswords("a" * 20, "a" * 20, "b" * 20)
    with pytest.raises(DatabaseRoleError, match="at least"):
        RolePasswords("short", "b" * 20, "c" * 20)
    assert "a" * 20 not in repr(RolePasswords("a" * 20, "b" * 20, "c" * 20))


def _set_role_urls(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> None:
    base = {
        "oscal_owner": "postgresql+psycopg://oscal_owner:owner-password-0001@db:5432/x_test",
        "oscal_runtime": "postgresql+psycopg://oscal_runtime:runtime-password-01@db:5432/x_test",
        "oscal_provisioner": (
            "postgresql+psycopg://oscal_provisioner:provisioner-pass-1@db:5432/x_test"
        ),
    }
    base.update(overrides)
    for role, variable in ROLE_URL_VARIABLES.items():
        monkeypatch.setenv(variable, base[role])


def test_role_harness_accepts_complete_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_role_urls(monkeypatch)
    assert set(load_role_urls() or {}) == set(ROLE_URL_VARIABLES)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {
                "oscal_runtime": "postgresql+psycopg://oscal_owner:runtime-password-01@db:5432/x_test"
            },
            "must authenticate as 'oscal_runtime'",
        ),
        (
            {"oscal_runtime": "postgresql+psycopg://oscal_runtime:runtime-password-01@db:5432/x"},
            "_test",
        ),
        (
            {
                "oscal_runtime": "postgresql+psycopg://oscal_runtime:runtime-password-01@db:5432/y_test"
            },
            "same _test database",
        ),
        (
            {
                "oscal_runtime": "postgresql+psycopg://oscal_runtime:owner-password-0001@db:5432/x_test"
            },
            "distinct password",
        ),
    ],
)
def test_role_harness_rejects_unsafe_configuration(
    monkeypatch: pytest.MonkeyPatch, overrides: dict[str, str], message: str
) -> None:
    _set_role_urls(monkeypatch, **overrides)
    with pytest.raises(RoleHarnessConfigurationError, match=message):
        load_role_urls()


def test_role_harness_rejects_partial_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_role_urls(monkeypatch)
    monkeypatch.delenv("TEST_DATABASE_PROVISIONER_URL")
    with pytest.raises(RoleHarnessConfigurationError, match="TEST_DATABASE_PROVISIONER_URL"):
        load_role_urls()
