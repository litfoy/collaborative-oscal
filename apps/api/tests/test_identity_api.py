from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.dependencies import get_current_identity
from app.domain.identity.models import UserIdentity
from app.main import app


def test_health_remains_public() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_me_rejects_missing_bearer_token() -> None:
    response = TestClient(app).get("/api/v1/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {"detail": "Authentication required."}


def test_me_hides_token_validation_details(monkeypatch) -> None:
    from app.api import dependencies
    from app.authentication.tokens import InvalidAccessToken

    class InvalidValidator:
        def validate(self, token: str):
            raise InvalidAccessToken("private verification detail")

    monkeypatch.setattr(dependencies, "get_access_token_validator", lambda: InvalidValidator())
    response = TestClient(app).get(
        "/api/v1/me",
        headers={"Authorization": "Bearer invalid"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid access token."}
    assert "private verification detail" not in response.text


def test_me_returns_only_the_authenticated_identity(monkeypatch) -> None:
    identity = UserIdentity(
        id=uuid4(),
        issuer="https://identity.example.test",
        subject="private-subject",
        display_name="Example User",
        email="user@example.test",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    app.dependency_overrides[get_current_identity] = lambda: identity
    try:
        response = TestClient(app).get("/api/v1/me")
    finally:
        app.dependency_overrides.pop(get_current_identity, None)

    assert response.status_code == 200
    assert response.json() == {
        "id": str(identity.id),
        "display_name": "Example User",
        "email": "user@example.test",
    }
    assert "subject" not in response.json()
    assert "issuer" not in response.json()
    assert "access_token" not in response.json()
    assert "created_at" not in response.json()


def test_openapi_documents_bearer_authentication() -> None:
    schema = app.openapi()

    assert schema["components"]["securitySchemes"]["HTTPBearer"]["scheme"] == "bearer"
