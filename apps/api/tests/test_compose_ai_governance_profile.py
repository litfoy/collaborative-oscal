from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
COMPOSE_FILE = ROOT / "compose.yaml"


def test_ai_governance_seed_service_is_profile_gated_and_one_shot() -> None:
    compose = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))
    services = compose["services"]

    seed_service = services["ai-governance-seed"]
    assert seed_service["profiles"] == ["ai-governance-demo"]
    assert seed_service["command"] == ["python", "-m", "app.cli", "seed-ai-governance-demo-local"]
    assert seed_service["restart"] == "no"
    assert seed_service["depends_on"]["db-init"]["condition"] == "service_completed_successfully"


def test_standard_compose_init_and_api_ordering_remains_unchanged() -> None:
    compose = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))
    services = compose["services"]

    db_init_command = services["db-init"]["command"][2]
    assert "alembic -c /opt/app/alembic.ini upgrade head" in db_init_command
    assert "python -m app.cli bootstrap-demo" in db_init_command
    assert "python /opt/compose/seed-demo-catalog.py" in db_init_command
    assert services["api"]["depends_on"]["db-init"]["condition"] == "service_completed_successfully"

