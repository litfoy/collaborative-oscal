# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

"""Add optimistic concurrency versions to Assessment Plans.

Revision ID: e1f2a3b4c5d6
Revises: d4e5f6a7b8c9
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: str | Sequence[str] | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "assessment_plans",
        sa.Column("concurrency_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_check_constraint(
        "ck_assessment_plans_concurrency_version",
        "assessment_plans",
        "concurrency_version >= 1",
    )
    op.alter_column("assessment_plans", "concurrency_version", server_default=None)


def downgrade() -> None:
    op.drop_constraint(
        "ck_assessment_plans_concurrency_version",
        "assessment_plans",
        type_="check",
    )
    op.drop_column("assessment_plans", "concurrency_version")
