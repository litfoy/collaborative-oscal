# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

from collections.abc import Callable
from dataclasses import dataclass
from hmac import compare_digest
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.application.authorization import AuthorizationService
from app.application.identity import IdentityService
from app.authentication.demo import (
    DEMO_ISSUER,
    DEMO_MEMBERSHIP_ID,
    DEMO_NAME,
    DEMO_SUBJECT,
    DEMO_TENANT_ID,
    DEMO_USER_ID,
    demo_state_valid,
)
from app.authentication.tokens import (
    AccessTokenValidator,
    AuthenticationConfigurationError,
    IdentityProviderUnavailable,
    InvalidAccessToken,
    get_access_token_validator,
)
from app.config import get_settings
from app.domain.identity.models import AuthorizedTenantContext, Permission, TenantRole, UserIdentity
from app.persistence.database import create_session_factory
from app.persistence.identity import SQLIdentityRepository, SQLMembershipRepository

bearer_security = HTTPBearer(auto_error=False, bearerFormat="JWT")


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    issuer: str
    subject: str
    display_name: str | None
    email: str | None


def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_security),
) -> AuthenticatedPrincipal:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    settings = get_settings()
    if settings.auth_mode == "demo":
        if not settings.demo_auth_secret or not compare_digest(
            credentials.credentials.encode("utf-8"), settings.demo_auth_secret.encode("utf-8")
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid access token.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return AuthenticatedPrincipal(DEMO_ISSUER, DEMO_SUBJECT, DEMO_NAME, None)

    try:
        validator: AccessTokenValidator = get_access_token_validator()
        claims = validator.validate(credentials.credentials)
    except InvalidAccessToken as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except (AuthenticationConfigurationError, IdentityProviderUnavailable) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is unavailable.",
        ) from exc

    name = claims.get("name")
    email = claims.get("email")
    return AuthenticatedPrincipal(
        issuer=claims["iss"],
        subject=claims["sub"],
        display_name=name if isinstance(name, str) and len(name) <= 255 else None,
        email=(
            email
            if claims.get("email_verified") is True and isinstance(email, str) and len(email) <= 320
            else None
        ),
    )


def get_current_identity(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> UserIdentity:
    with create_session_factory().begin() as session:
        if get_settings().auth_mode == "demo":
            if (
                principal.issuer != DEMO_ISSUER
                or principal.subject != DEMO_SUBJECT
                or not demo_state_valid(session)
            ):
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Demo identity is not provisioned or has conflicting authorization.",
                )
            identity = SQLIdentityRepository(session).get_by_id(DEMO_USER_ID)
            if identity is None:
                raise HTTPException(status_code=503, detail="Demo identity is unavailable.")
            return identity
        return IdentityService(SQLIdentityRepository(session)).resolve_identity(
            issuer=principal.issuer,
            subject=principal.subject,
            display_name=principal.display_name,
            email=principal.email,
        )


def require_tenant_permission(
    permission: Permission,
) -> Callable[..., AuthorizedTenantContext]:
    def dependency(
        tenant_id: UUID,
        identity: UserIdentity = Depends(get_current_identity),
    ) -> AuthorizedTenantContext:
        if get_settings().auth_mode == "demo" and tenant_id != DEMO_TENANT_ID:
            raise HTTPException(status_code=403, detail="Tenant access denied.")
        with create_session_factory().begin() as session:
            context = AuthorizationService().resolve_tenant_context(
                SQLMembershipRepository(session),
                tenant_id=tenant_id,
                user_id=identity.id,
                required_permission=permission,
            )
            if (
                get_settings().auth_mode == "demo"
                and context is not None
                and (
                    context.membership.id != DEMO_MEMBERSHIP_ID
                    or context.membership.role != TenantRole.CATALOG_EDITOR
                )
            ):
                context = None
        if context is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tenant access denied.",
            )
        return context

    return dependency
