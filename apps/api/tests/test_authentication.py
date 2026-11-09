import json
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.authentication.tokens import (
    AccessTokenValidator,
    AuthenticationConfigurationError,
    InvalidAccessToken,
)
from app.config import Settings


class _OIDCState:
    def __init__(self) -> None:
        self.keys: list[dict] = []
        self.discovery_issuer = ""
        self.discovery_requests = 0


class _OIDCHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        state: _OIDCState = self.server.oidc_state
        if self.path.endswith("/.well-known/openid-configuration"):
            state.discovery_requests += 1
            issuer = urlsplit(state.discovery_issuer)
            payload = {
                "issuer": state.discovery_issuer,
                "jwks_uri": f"{issuer.scheme}://{issuer.netloc}/jwks",
            }
        elif self.path == "/jwks":
            payload = {"keys": state.keys}
        else:
            self.send_error(404)
            return
        content = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args) -> None:
        return


@pytest.fixture
def oidc_server():
    state = _OIDCState()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _OIDCHandler)
    server.oidc_state = state
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state.discovery_issuer = f"http://127.0.0.1:{server.server_port}/realms/test"
    try:
        yield state
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


@pytest.fixture
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwk(private_key, key_id: str) -> dict:
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk.update({"kid": key_id, "use": "sig", "alg": "RS256"})
    return jwk


def _settings(issuer: str, **values) -> Settings:
    return Settings(
        _env_file=None,
        oidc_issuer_url=issuer,
        oidc_api_audience="collaborative-oscal-api",
        oidc_clock_skew_seconds=0,
        oidc_jwks_refresh_cooldown_seconds=0,
        oidc_http_timeout_seconds=2,
        **values,
    )


def _claims(issuer: str, **overrides) -> dict:
    claims = {
        "iss": issuer,
        "sub": "external-user-123",
        "aud": "collaborative-oscal-api",
        "exp": datetime.now(UTC) + timedelta(minutes=5),
        "nbf": datetime.now(UTC) - timedelta(seconds=1),
        "typ": "Bearer",
        "name": "Example User",
        "email": "user@example.test",
        "email_verified": True,
    }
    claims.update(overrides)
    return claims


def _token(private_key, claims: dict, *, key_id: str = "key-1", **headers) -> str:
    return jwt.encode(
        claims,
        private_key,
        algorithm="RS256",
        headers={"kid": key_id, **headers},
    )


def test_valid_access_token_is_accepted(oidc_server, signing_key) -> None:
    oidc_server.keys = [_jwk(signing_key, "key-1")]
    validator = AccessTokenValidator(_settings(oidc_server.discovery_issuer))
    claims = validator.validate(_token(signing_key, _claims(oidc_server.discovery_issuer)))

    assert claims["sub"] == "external-user-123"
    assert oidc_server.discovery_requests == 1


@pytest.mark.parametrize(
    "claim_overrides",
    [
        {"exp": datetime.now(UTC) - timedelta(minutes=1)},
        {"iss": "https://untrusted.example.test"},
        {"aud": "another-api"},
        {"nbf": datetime.now(UTC) + timedelta(minutes=1)},
        {"sub": ""},
        {"sub": "x" * 256},
        {"typ": "ID"},
    ],
)
def test_invalid_access_token_claims_are_rejected(
    oidc_server, signing_key, claim_overrides
) -> None:
    oidc_server.keys = [_jwk(signing_key, "key-1")]
    validator = AccessTokenValidator(_settings(oidc_server.discovery_issuer))
    token = _token(
        signing_key,
        _claims(oidc_server.discovery_issuer, **claim_overrides),
    )

    with pytest.raises(InvalidAccessToken):
        validator.validate(token)


def test_missing_subject_and_id_token_substitution_are_rejected(oidc_server, signing_key) -> None:
    oidc_server.keys = [_jwk(signing_key, "key-1")]
    validator = AccessTokenValidator(_settings(oidc_server.discovery_issuer))
    claims_without_subject = _claims(oidc_server.discovery_issuer)
    claims_without_subject.pop("sub")
    missing_subject = _token(signing_key, claims_without_subject)
    id_token = _token(
        signing_key,
        _claims(oidc_server.discovery_issuer, typ="ID"),
    )

    for token in (missing_subject, id_token):
        with pytest.raises(InvalidAccessToken):
            validator.validate(token)


def test_unsupported_and_unsigned_algorithms_are_rejected(oidc_server, signing_key) -> None:
    oidc_server.keys = [_jwk(signing_key, "key-1")]
    validator = AccessTokenValidator(_settings(oidc_server.discovery_issuer))
    claims = _claims(oidc_server.discovery_issuer)
    hmac_token = jwt.encode(
        claims,
        "not-a-trusted-key-that-is-at-least-thirty-two-bytes",
        algorithm="HS256",
        headers={"kid": "key-1"},
    )
    unsigned_token = jwt.encode(claims, key="", algorithm="none", headers={"kid": "key-1"})

    for token in (hmac_token, unsigned_token):
        with pytest.raises(InvalidAccessToken):
            validator.validate(token)


def test_token_algorithm_must_match_jwk_algorithm(oidc_server, signing_key) -> None:
    oidc_server.keys = [_jwk(signing_key, "key-1")]
    validator = AccessTokenValidator(
        _settings(
            oidc_server.discovery_issuer,
            oidc_allowed_algorithms=["RS256", "RS512"],
        )
    )
    token = jwt.encode(
        _claims(oidc_server.discovery_issuer),
        signing_key,
        algorithm="RS512",
        headers={"kid": "key-1"},
    )

    with pytest.raises(InvalidAccessToken, match="does not match"):
        validator.validate(token)


def test_invalid_signature_and_unknown_signing_key_are_rejected(oidc_server, signing_key) -> None:
    oidc_server.keys = [_jwk(signing_key, "key-1")]
    validator = AccessTokenValidator(_settings(oidc_server.discovery_issuer))
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    bad_signature = _token(other_key, _claims(oidc_server.discovery_issuer))
    unknown_key = _token(other_key, _claims(oidc_server.discovery_issuer), key_id="unknown")

    with pytest.raises(InvalidAccessToken):
        validator.validate(bad_signature)
    with pytest.raises(InvalidAccessToken):
        validator.validate(unknown_key)


def test_key_rotation_refreshes_the_jwks_cache(oidc_server, signing_key) -> None:
    oidc_server.keys = [_jwk(signing_key, "key-1")]
    validator = AccessTokenValidator(_settings(oidc_server.discovery_issuer))
    validator.validate(_token(signing_key, _claims(oidc_server.discovery_issuer)))

    rotated_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    oidc_server.keys = [_jwk(rotated_key, "key-2")]
    claims = validator.validate(
        _token(rotated_key, _claims(oidc_server.discovery_issuer), key_id="key-2")
    )

    assert claims["sub"] == "external-user-123"


def test_rfc9068_profile_requires_access_token_type_and_claims(oidc_server, signing_key) -> None:
    oidc_server.keys = [_jwk(signing_key, "key-1")]
    validator = AccessTokenValidator(
        _settings(oidc_server.discovery_issuer, oidc_access_token_profile="rfc9068")
    )
    claims = _claims(
        oidc_server.discovery_issuer,
        client_id="collaborative-oscal-dev",
        iat=datetime.now(UTC),
        jti="token-id",
    )
    valid_token = _token(signing_key, claims, typ="at+jwt")
    id_token = _token(signing_key, claims, typ="JWT")

    assert validator.validate(valid_token)["client_id"] == "collaborative-oscal-dev"
    with pytest.raises(InvalidAccessToken):
        validator.validate(id_token)


def test_configured_jwks_endpoint_cannot_change_issuer_origin(oidc_server) -> None:
    with pytest.raises(AuthenticationConfigurationError):
        AccessTokenValidator(
            _settings(
                oidc_server.discovery_issuer,
                oidc_jwks_url="https://attacker.example.test/keys",
            )
        )


def test_custom_profile_cannot_use_a_non_discriminating_registered_claim(oidc_server) -> None:
    with pytest.raises(ValueError, match="provider-specific"):
        _settings(
            oidc_server.discovery_issuer,
            oidc_access_token_type_claim="aud",
        )


def test_discovery_issuer_must_match_configured_issuer(oidc_server) -> None:
    configured_issuer = oidc_server.discovery_issuer
    oidc_server.discovery_issuer = f"{configured_issuer}/other"

    with pytest.raises(AuthenticationConfigurationError, match="does not match"):
        AccessTokenValidator(_settings(configured_issuer))
