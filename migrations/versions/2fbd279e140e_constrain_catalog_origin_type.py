"""constrain catalog origin type

Revision ID: 2fbd279e140e
Revises: f27461c200f9
Create Date: 2026-11-09 23:09:24.201475

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '2fbd279e140e'
down_revision: Union[str, Sequence[str], None] = 'f27461c200f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_check_constraint(
        "ck_catalogs_origin_type",
        "catalogs",
        "origin_type IN ('imported', 'custom')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_catalogs_origin_type", "catalogs", type_="check")
