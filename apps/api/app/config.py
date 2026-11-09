from __future__ import annotations

from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../../.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_cors_origins: list[str] = ["http://localhost:3000"]
    database_url: str | None = None
    postgres_db: str | None = None
    postgres_user: str | None = None
    postgres_password: str | None = None
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    oidc_issuer_url: str | None = Field(default=None, max_length=2048)
    oidc_api_audience: str | None = Field(default=None, min_length=1, max_length=255)
    oidc_jwks_url: str | None = None
    oidc_allowed_algorithms: list[str] = ["RS256"]
    oidc_clock_skew_seconds: int = Field(default=30, ge=0, le=300)
    oidc_jwks_cache_seconds: int = Field(default=300, ge=1, le=3600)
    oidc_jwks_refresh_cooldown_seconds: int = Field(default=5, ge=0, le=60)
    oidc_http_timeout_seconds: float = Field(default=5, gt=0, le=30)
    oidc_access_token_profile: Literal["custom", "rfc9068"] = "custom"
    oidc_access_token_type_claim: str = Field(default="typ", min_length=1, max_length=255)
    oidc_access_token_type_value: str = Field(default="Bearer", min_length=1, max_length=255)

    @field_validator("oidc_issuer_url", "oidc_jwks_url")
    @classmethod
    def validate_oidc_urls(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        local_hosts = {"localhost", "127.0.0.1", "::1"}
        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or (parsed.scheme != "https" and parsed.hostname not in local_hosts)
        ):
            raise ValueError("OIDC URLs must use HTTPS, except for loopback development URLs.")
        return value

    @field_validator("oidc_allowed_algorithms")
    @classmethod
    def validate_oidc_algorithms(cls, value: list[str]) -> list[str]:
        supported = {
            "RS256",
            "RS384",
            "RS512",
            "PS256",
            "PS384",
            "PS512",
            "ES256",
            "ES384",
            "ES512",
            "EdDSA",
        }
        if not value or len(value) != len(set(value)) or not set(value) <= supported:
            raise ValueError("Configure one or more supported asymmetric JWT algorithms.")
        return value

    @model_validator(mode="after")
    def validate_custom_access_token_profile(self) -> Settings:
        reserved_claims = {
            "iss",
            "sub",
            "exp",
            "nbf",
            "aud",
            "iat",
            "jti",
            "nonce",
            "client_id",
        }
        if (
            self.oidc_access_token_profile == "custom"
            and self.oidc_access_token_type_claim in reserved_claims
        ):
            raise ValueError("Configure a provider-specific access-token discriminator claim.")
        return self

    def get_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        if not self.postgres_db or not self.postgres_user or not self.postgres_password:
            raise RuntimeError(
                "Configure DATABASE_URL or POSTGRES_DB, POSTGRES_USER, and POSTGRES_PASSWORD."
            )
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        ).render_as_string(hide_password=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
