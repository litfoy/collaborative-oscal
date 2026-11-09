from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.application.authorization import AuthorizationService
from app.application.identity import IdentityService
from app.authentication.tokens import (
    AccessTokenValidator,
    AuthenticationConfigurationError,
    IdentityProviderUnavailable,
    InvalidAccessToken,
    get_access_token_validator,
)
from app.domain.identity.models import AuthorizedTenantContext, Permission, UserIdentity
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
        with create_session_factory().begin() as session:
            context = AuthorizationService().resolve_tenant_context(
                SQLMembershipRepository(session),
                tenant_id=tenant_id,
                user_id=identity.id,
                required_permission=permission,
            )
        if context is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tenant access denied.",
            )
        return context

    return dependency
