from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from collaborative_oscal_oscal.catalog_import import DEFAULT_MAX_INPUT_BYTES
from pydantic import ValidationError

from app.application.catalog_import import CatalogImportMetadata
from app.cli import _import_catalog
from app.config import Settings


def test_import_limit_default_supports_bsi_catalog() -> None:
    assert Settings().catalog_import_max_input_bytes == 100 * 1024 * 1024
    assert DEFAULT_MAX_INPUT_BYTES == 100 * 1024 * 1024


def test_import_limit_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CATALOG_IMPORT_MAX_INPUT_BYTES", "10485760")
    assert Settings().catalog_import_max_input_bytes == 10485760


@pytest.mark.parametrize("limit", [0, 100 * 1024 * 1024 + 1])
def test_import_limit_bounds(limit: int) -> None:
    with pytest.raises(ValidationError):
        Settings(catalog_import_max_input_bytes=limit)


def test_cli_passes_limit_to_import_service(tmp_path: Path) -> None:
    source = tmp_path / "catalog.json"
    source.write_bytes(b"{}")
    settings = Mock(catalog_import_max_input_bytes=10485760)
    with (
        patch("app.cli.get_settings", return_value=settings),
        patch("app.cli.create_unit_of_work_factory") as factory,
        patch("app.cli.CatalogImportService") as service,
    ):
        _import_catalog(
            tenant_id=uuid4(),
            path=source,
            metadata=CatalogImportMetadata(),
            target_catalog_id=None,
        )
    service.assert_called_once_with(factory.return_value, max_input_bytes=10485760)
