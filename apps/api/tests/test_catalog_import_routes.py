from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api import catalog_import_routes
from app.application.catalog_import import CatalogImportService, CatalogImportValidationError
from app.config import Settings
from app.main import app


@pytest.fixture
def import_client(monkeypatch):
    tenant_id = uuid4()
    app.dependency_overrides[catalog_import_routes.require_catalog_import] = (
        lambda: SimpleNamespace(tenant_id=tenant_id)
    )
    monkeypatch.setattr(catalog_import_routes, "create_unit_of_work_factory", lambda: None)
    monkeypatch.setattr(
        catalog_import_routes, "get_settings", lambda: Settings(catalog_import_max_input_bytes=512)
    )
    yield TestClient(app), tenant_id
    app.dependency_overrides.clear()


def test_import_forwards_original_bytes_and_target(import_client, monkeypatch):
    client, tenant_id = import_client
    catalog_id, revision_id, document_id = uuid4(), uuid4(), uuid4()
    result = SimpleNamespace(
        catalog=SimpleNamespace(id=catalog_id, name="Actual catalog"),
        revision=SimpleNamespace(
            id=revision_id,
            revision_number=2,
            oscal_document_uuid=document_id,
            oscal_version="1.1.3",
            source_version="2025",
        ),
        control_count=3,
        created=False,
    )
    service = Mock()
    service.import_catalog.return_value = result
    monkeypatch.setattr(catalog_import_routes, "CatalogImportService", lambda *a, **k: service)
    raw = b'{ "catalog": { "metadata": { "oscal-version": "1.1.3" } } }'
    response = client.post(
        f"/api/v1/tenants/{tenant_id}/catalogs/{catalog_id}/import",
        content=raw,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json()["revision_id"] == str(revision_id)
    assert response.json()["created"] is False
    service.import_catalog.assert_called_once_with(
        tenant_id, raw, "json", target_catalog_id=catalog_id
    )


def test_import_reports_validation_and_size_errors(import_client, monkeypatch):
    client, tenant_id = import_client
    path = f"/api/v1/tenants/{tenant_id}/catalogs/import"
    validation = CatalogImportService(lambda: None).validate_catalog(b"{", "json").result
    service = Mock()
    service.import_catalog.side_effect = CatalogImportValidationError(validation)
    monkeypatch.setattr(catalog_import_routes, "CatalogImportService", lambda *a, **k: service)
    headers = {"content-type": "application/json"}
    response = client.post(path, content=b"{", headers=headers)
    assert response.status_code == 422
    assert response.json()["detail"]["errors"][0]["message"].startswith("JSON syntax is invalid")
    assert client.post(path, content=b"x" * 513, headers=headers).status_code == 413
    response = client.post(path, content=b"{}", headers={"content-type": "text/plain"})
    assert response.status_code == 415
