import importlib.util
import re
import stat
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "infrastructure/docker/init-credentials.py"
spec = importlib.util.spec_from_file_location("compose_credentials", SCRIPT)
assert spec and spec.loader
credentials = importlib.util.module_from_spec(spec)
spec.loader.exec_module(credentials)


@pytest.fixture
def paths(tmp_path, monkeypatch):
    directory = tmp_path / "credentials"
    database = tmp_path / "database"
    directory.mkdir()
    database.mkdir()
    monkeypatch.setattr(credentials, "CREDENTIALS", directory)
    monkeypatch.setattr(credentials, "DATABASE", database)
    ownership = []
    monkeypatch.setattr(credentials.os, "chown", lambda *args: ownership.append(args))
    return directory, database, ownership


def test_generated_credentials_are_private_and_persistent(paths):
    directory, database, ownership = paths
    credentials.initialize()
    password = directory / "postgres-password"
    secret = directory / "demo-auth-secret"
    before = [path.read_text() for path in (password, secret)]
    assert all(re.fullmatch(r"[0-9a-f]{64}", value) for value in before)
    assert before[0] != before[1]
    assert stat.S_IMODE(directory.stat().st_mode) == 0o711
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o440 for path in (password, secret))
    assert ownership == [(password, 0, 10002), (secret, 0, 10001)]
    (database / "PG_VERSION").write_text("17")
    credentials.initialize()
    assert [path.read_text() for path in (password, secret)] == before


def test_missing_database_credential_does_not_replace_existing_data(paths):
    directory, database, _ = paths
    (database / "PG_VERSION").write_text("17")
    with pytest.raises(RuntimeError, match="credential is missing"):
        credentials.initialize()
    assert list(directory.iterdir()) == []


def test_invalid_existing_credential_fails_closed(paths):
    directory, _, _ = paths
    password = directory / "postgres-password"
    password.write_text("invalid")
    with pytest.raises(RuntimeError, match="Invalid credential file"):
        credentials.initialize()
    assert password.read_text() == "invalid"
