from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.dependencies import get_current_identity
from app.domain.identity.models import UserIdentity

router = APIRouter(prefix="/api/v1")


class IdentityResponse(BaseModel):
    id: UUID
    display_name: str | None
    email: str | None

    @classmethod
    def from_identity(cls, identity: UserIdentity) -> IdentityResponse:
        return cls(
            id=identity.id,
            display_name=identity.display_name,
            email=identity.email,
        )


@router.get("/me", response_model=IdentityResponse, tags=["identity"])
def get_me(identity: UserIdentity = Depends(get_current_identity)) -> IdentityResponse:
    return IdentityResponse.from_identity(identity)
