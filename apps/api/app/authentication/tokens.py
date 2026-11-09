from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from functools import lru_cache
from typing import Any
from urllib.parse import urlsplit

import jwt
from jwt import PyJWKClient
from jwt.exceptions import (
    PyJWKClientConnectionError,
    PyJWKClientError,
    PyJWTError,
)

from app.config import Settings, get_settings

_MAX_METADATA_BYTES = 1_048_576
_MAX_TOKEN_BYTES = 65_536
_RFC9068_REQUIRED_CLAIMS = ("iss", "exp", "aud", "sub", "client_id", "iat", "jti")


class AuthenticationConfigurationError(RuntimeError):
    pass


class IdentityProviderUnavailable(RuntimeError):
    pass


class InvalidAccessToken(ValueError):
    pass


def _origin(url: str) -> tuple[str, str, int]:
    parsed = urlsplit(url)
    if not parsed.scheme or not parsed.hostname:
        raise AuthenticationConfigurationError("OIDC endpoint URL is invalid.")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return parsed.scheme, parsed.hostname.casefold(), port


def _validate_endpoint_url(url: str, issuer: str) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or (parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"})
    ):
        raise AuthenticationConfigurationError("OIDC endpoint URL is not permitted.")
    try:
        if _origin(url) != _origin(issuer):
            raise AuthenticationConfigurationError(
                "OIDC discovery and JWKS endpoints must use the configured issuer origin."
            )
    except ValueError as exc:
        raise AuthenticationConfigurationError("OIDC endpoint URL is invalid.") from exc


def _read_json(url: str, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    opener = urllib.request.build_opener(_NoRedirectHandler())
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read(_MAX_METADATA_BYTES + 1)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise IdentityProviderUnavailable("OIDC metadata could not be retrieved.") from exc
    if len(body) > _MAX_METADATA_BYTES:
        raise AuthenticationConfigurationError("OIDC metadata response is too large.")
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AuthenticationConfigurationError("OIDC metadata is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise AuthenticationConfigurationError("OIDC metadata must be a JSON object.")
    return payload


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


class BoundedPyJWKClient(PyJWKClient):
    def fetch_data(self) -> Any:
        request = urllib.request.Request(url=self.uri, headers=self.headers)
        handlers: list[Any] = [_NoRedirectHandler()]
        if self.ssl_context is not None:
            handlers.append(urllib.request.HTTPSHandler(context=self.ssl_context))
        opener = urllib.request.build_opener(*handlers)
        try:
            with opener.open(request, timeout=self.timeout) as response:
                body = response.read(_MAX_METADATA_BYTES + 1)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise PyJWKClientConnectionError("Unable to retrieve the configured JWKS.") from exc
        if len(body) > _MAX_METADATA_BYTES:
            raise PyJWKClientError("The configured JWKS response is too large.")
        try:
            jwk_set = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise PyJWKClientError("The configured JWKS response is not valid JSON.") from exc
        jwk_set = self._as_jwk_set_payload(jwk_set)
        if self.jwk_set_cache is not None:
            self.jwk_set_cache.put(jwk_set)
        self._last_successful_fetch = time.monotonic()
        return jwk_set


class AccessTokenValidator:
    def __init__(self, settings: Settings) -> None:
        if not settings.oidc_issuer_url or not settings.oidc_api_audience:
            raise AuthenticationConfigurationError(
                "Configure OIDC_ISSUER_URL and OIDC_API_AUDIENCE to enable protected endpoints."
            )
        self._settings = settings
        self._issuer = settings.oidc_issuer_url
        self._audience = settings.oidc_api_audience
        self._algorithms = settings.oidc_allowed_algorithms
        _validate_endpoint_url(self._issuer, self._issuer)
        if settings.oidc_jwks_url:
            jwks_url = settings.oidc_jwks_url
            _validate_endpoint_url(jwks_url, self._issuer)
        else:
            discovery_url = f"{self._issuer.rstrip('/')}/.well-known/openid-configuration"
            metadata = _read_json(discovery_url, settings.oidc_http_timeout_seconds)
            if metadata.get("issuer") != self._issuer:
                raise AuthenticationConfigurationError(
                    "OIDC discovery issuer does not match OIDC_ISSUER_URL."
                )
            jwks_url = metadata.get("jwks_uri")
            if not isinstance(jwks_url, str):
                raise AuthenticationConfigurationError("OIDC discovery has no JWKS URI.")
            _validate_endpoint_url(jwks_url, self._issuer)
        self._jwks_client = BoundedPyJWKClient(
            jwks_url,
            cache_jwk_set=True,
            lifespan=settings.oidc_jwks_cache_seconds,
            timeout=settings.oidc_http_timeout_seconds,
            cooldown_duration=settings.oidc_jwks_refresh_cooldown_seconds,
        )

    def validate(self, token: str) -> dict[str, Any]:
        if not token or len(token.encode("utf-8")) > _MAX_TOKEN_BYTES:
            raise InvalidAccessToken("Invalid access token.")
        try:
            header = jwt.get_unverified_header(token)
        except PyJWTError as exc:
            raise InvalidAccessToken("Invalid access token.") from exc
        algorithm = header.get("alg")
        key_id = header.get("kid")
        if (
            algorithm not in self._algorithms
            or not isinstance(key_id, str)
            or not key_id
            or len(key_id) > 255
            or any(name in header for name in ("jku", "jwk", "x5u", "crit"))
        ):
            raise InvalidAccessToken("Invalid access token.")

        if self._settings.oidc_access_token_profile == "rfc9068":
            token_type = header.get("typ")
            if not isinstance(token_type, str) or token_type.lower() not in {
                "at+jwt",
                "application/at+jwt",
            }:
                raise InvalidAccessToken("Token does not use the configured RFC 9068 profile.")
            required_claims = _RFC9068_REQUIRED_CLAIMS
        else:
            required_claims = ("iss", "exp", "aud", "sub")

        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
        except PyJWKClientConnectionError as exc:
            raise IdentityProviderUnavailable("OIDC signing keys are unavailable.") from exc
        except PyJWKClientError as exc:
            raise InvalidAccessToken("Token signing key is not trusted.") from exc

        key_algorithm = signing_key._jwk_data.get("alg")
        if key_algorithm is not None and key_algorithm != algorithm:
            raise InvalidAccessToken("Token algorithm does not match the selected signing key.")

        try:
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=self._algorithms,
                issuer=self._issuer,
                audience=self._audience,
                leeway=self._settings.oidc_clock_skew_seconds,
                options={"require": list(required_claims)},
            )
        except PyJWTError as exc:
            raise InvalidAccessToken("Invalid access token.") from exc

        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject or len(subject) > 255:
            raise InvalidAccessToken("Invalid access token subject.")
        if self._settings.oidc_access_token_profile == "custom":
            token_type = claims.get(self._settings.oidc_access_token_type_claim)
            if token_type != self._settings.oidc_access_token_type_value:
                raise InvalidAccessToken("Token does not use the configured access-token profile.")
        elif not all(
            isinstance(claims.get(name), str) and claims[name] for name in ("client_id", "jti")
        ):
            raise InvalidAccessToken("Invalid RFC 9068 access token.")
        return claims


@lru_cache(maxsize=1)
def get_access_token_validator() -> AccessTokenValidator:
    return AccessTokenValidator(get_settings())
