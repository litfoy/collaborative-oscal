from typing import Protocol

from app.domain.identity.models import UserIdentity


class IdentityRepository(Protocol):
    def get_or_create(
        self,
        *,
        issuer: str,
        subject: str,
        display_name: str | None,
        email: str | None,
    ) -> UserIdentity: ...


class IdentityService:
    def __init__(self, identities: IdentityRepository) -> None:
        self._identities = identities

    def resolve_identity(
        self,
        *,
        issuer: str,
        subject: str,
        display_name: str | None,
        email: str | None,
    ) -> UserIdentity:
        return self._identities.get_or_create(
            issuer=issuer,
            subject=subject,
            display_name=display_name,
            email=email,
        )
