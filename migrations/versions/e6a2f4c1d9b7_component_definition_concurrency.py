# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

"""add optimistic concurrency to component definitions

Revision ID: e6a2f4c1d9b7
Revises: c92e1b7d4f33
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e6a2f4c1d9b7"
down_revision: str | Sequence[str] | None = "c92e1b7d4f33"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "component_definitions",
        sa.Column("concurrency_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_check_constraint(
        "ck_component_definitions_concurrency_version",
        "component_definitions",
        "concurrency_version >= 1",
    )
    op.alter_column("component_definitions", "concurrency_version", server_default=None)


def downgrade() -> None:
    op.drop_constraint(
        "ck_component_definitions_concurrency_version",
        "component_definitions",
        type_="check",
    )
    op.drop_column("component_definitions", "concurrency_version")

