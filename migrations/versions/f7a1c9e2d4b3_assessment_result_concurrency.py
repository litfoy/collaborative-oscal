"""Add optimistic concurrency versions to Assessment Results.

Revision ID: f7a1c9e2d4b3
Revises: e1f2a3b4c5d6
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f7a1c9e2d4b3"
down_revision: str | Sequence[str] | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "assessment_results",
        sa.Column("concurrency_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_check_constraint(
        "ck_assessment_results_concurrency_version",
        "assessment_results",
        "concurrency_version >= 1",
    )
    op.alter_column("assessment_results", "concurrency_version", server_default=None)


def downgrade() -> None:
    op.drop_constraint(
        "ck_assessment_results_concurrency_version",
        "assessment_results",
        type_="check",
    )
    op.drop_column("assessment_results", "concurrency_version")

