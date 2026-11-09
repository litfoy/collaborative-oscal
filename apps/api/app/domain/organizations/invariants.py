from collections.abc import Callable
from uuid import UUID

from app.domain.errors import DomainInvariantError, EntityNotFoundError


def validate_parent_chain(
    organization_id: UUID,
    parent_organization_id: UUID | None,
    get_parent_id: Callable[[UUID], UUID | None],
) -> None:
    """Reject self-parenting and cycles in an existing parent chain."""
    visited = {organization_id}
    current_id = parent_organization_id
    while current_id is not None:
        if current_id in visited:
            raise DomainInvariantError("Organization hierarchy cannot contain cycles.")
        visited.add(current_id)
        try:
            current_id = get_parent_id(current_id)
        except EntityNotFoundError as error:
            raise DomainInvariantError("Organization parent is not in this tenant.") from error
