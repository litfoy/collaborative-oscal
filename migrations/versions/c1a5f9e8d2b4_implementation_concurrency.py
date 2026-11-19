# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

"""Add optimistic concurrency version to control implementations.

Revision ID: c1a5f9e8d2b4
Revises: a4b9e8c7d6f1
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c1a5f9e8d2b4"
down_revision: str | Sequence[str] | None = "a4b9e8c7d6f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "control_implementations",
        sa.Column("concurrency_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_check_constraint(
        "ck_implementations_concurrency_version",
        "control_implementations",
        "concurrency_version >= 1",
    )
    op.alter_column("control_implementations", "concurrency_version", server_default=None)


def downgrade() -> None:
    op.drop_constraint(
        "ck_implementations_concurrency_version",
        "control_implementations",
        type_="check",
    )
    op.drop_column("control_implementations", "concurrency_version")


