"""Add optimistic concurrency versions to System Security Plans.

Revision ID: a91f6c2d4e8b
Revises: f7a1c9e2d4b3
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a91f6c2d4e8b"
down_revision: str | Sequence[str] | None = "f7a1c9e2d4b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "system_security_plans",
        sa.Column("concurrency_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_check_constraint(
        "ck_system_security_plans_concurrency_version",
        "system_security_plans",
        "concurrency_version >= 1",
    )
    op.alter_column("system_security_plans", "concurrency_version", server_default=None)


def downgrade() -> None:
    op.drop_constraint(
        "ck_system_security_plans_concurrency_version",
        "system_security_plans",
        type_="check",
    )
    op.drop_column("system_security_plans", "concurrency_version")

