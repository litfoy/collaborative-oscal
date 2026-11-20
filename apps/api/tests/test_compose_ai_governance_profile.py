# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
COMPOSE_FILE = ROOT / "compose.yaml"


def test_ai_governance_seed_runs_during_standard_db_init() -> None:
    compose = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))
    services = compose["services"]

    db_init_command = services["db-init"]["command"][2]
    assert "python -m app.cli seed-ai-governance-demo-local" in db_init_command
    assert "ai-governance-seed" not in services


def test_standard_compose_init_and_api_ordering_remains_unchanged() -> None:
    compose = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))
    services = compose["services"]

    db_init_command = services["db-init"]["command"][2]
    assert "alembic -c /opt/app/alembic.ini upgrade head" in db_init_command
    assert "python -m app.cli bootstrap-demo" in db_init_command
    assert "python /opt/compose/seed-demo-catalog.py" in db_init_command
    assert "python -m app.cli seed-ai-governance-demo-local" in db_init_command
    assert services["api"]["depends_on"]["db-init"]["condition"] == "service_completed_successfully"

