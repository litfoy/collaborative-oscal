# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, insert, select, text

from app.persistence.models import (
    CatalogControlIndexRecord,
    CatalogGroupIndexRecord,
    CatalogRecord,
    CatalogRevisionRecord,
    TenantRecord,
)

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "compose_seed", ROOT / "infrastructure/docker/seed-demo-catalog.py"
)
assert spec and spec.loader
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)
CATALOG = ROOT / "examples/catalogs/sample-data-handling.json"


@pytest.fixture
def seed_context(db_engine, monkeypatch):
    tenant_id = uuid4()
    document_uuid = UUID(json.loads(CATALOG.read_bytes())["catalog"]["uuid"])
    monkeypatch.setattr(seed, "DEMO_TENANT_ID", tenant_id)
    monkeypatch.setattr(seed, "CATALOG_UUID", document_uuid)
    monkeypatch.setattr(seed, "SEED_NAME", str(uuid4()))
    monkeypatch.setattr(seed, "get_settings", lambda: SimpleNamespace(auth_mode="demo"))
    with db_engine.connect() as connection:
        transaction = connection.begin()
        now = datetime.now(UTC)
        connection.execute(
            insert(TenantRecord).values(
                id=tenant_id,
                name="Seed test",
                slug=str(tenant_id),
                created_at=now,
                updated_at=now,
            )
        )
        try:
            yield connection, tenant_id
        finally:
            transaction.rollback()


def catalog_count(connection, tenant_id):
    return connection.scalar(
        select(func.count()).select_from(CatalogRecord).where(CatalogRecord.tenant_id == tenant_id)
    )


def test_seed_is_idempotent_and_does_not_restore_removed_catalog(seed_context):
    connection, tenant_id = seed_context
    assert seed.seed_catalog(connection, CATALOG)
    assert not seed.seed_catalog(connection, CATALOG)
    assert catalog_count(connection, tenant_id) == 1
    revision = connection.execute(
        select(CatalogRevisionRecord).where(CatalogRevisionRecord.tenant_id == tenant_id)
    ).first()
    assert revision is not None
    assert revision.oscal_document_uuid == seed.CATALOG_UUID
    connection.execute(
        text("DELETE FROM compose_demo_seeds WHERE name = :name"), {"name": seed.SEED_NAME}
    )
    assert not seed.seed_catalog(connection, CATALOG)
    assert catalog_count(connection, tenant_id) == 1
    for model in (
        CatalogControlIndexRecord,
        CatalogGroupIndexRecord,
        CatalogRevisionRecord,
        CatalogRecord,
    ):
        connection.execute(delete(model).where(model.tenant_id == tenant_id))
    assert not seed.seed_catalog(connection, CATALOG)
    assert catalog_count(connection, tenant_id) == 0


def test_failed_seed_rolls_back_catalog_and_marker(seed_context, monkeypatch):
    connection, tenant_id = seed_context
    original = seed.CatalogImportService.import_catalog

    def fail_after_import(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(seed.CatalogImportService, "import_catalog", fail_after_import)
    with pytest.raises(RuntimeError, match="simulated failure"), connection.begin_nested():
        seed.seed_catalog(connection, CATALOG)
    assert catalog_count(connection, tenant_id) == 0
    monkeypatch.setattr(seed.CatalogImportService, "import_catalog", original)
    assert seed.seed_catalog(connection, CATALOG)
    assert catalog_count(connection, tenant_id) == 1


def test_seed_rejects_non_demo_mode(monkeypatch):
    monkeypatch.setattr(seed, "get_settings", lambda: SimpleNamespace(auth_mode="keycloak"))
    with pytest.raises(RuntimeError, match="requires AUTH_MODE=demo"):
        seed.seed_catalog(None, CATALOG)
