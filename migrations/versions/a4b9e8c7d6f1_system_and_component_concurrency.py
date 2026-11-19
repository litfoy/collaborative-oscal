# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

"""Add optimistic concurrency versions to Systems and System Components.

Revision ID: a4b9e8c7d6f1
Revises: e6a2f4c1d9b7
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a4b9e8c7d6f1"
down_revision: str | Sequence[str] | None = "e6a2f4c1d9b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "information_systems",
        sa.Column("concurrency_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "system_components",
        sa.Column("concurrency_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_check_constraint(
        "ck_information_systems_concurrency_version",
        "information_systems",
        "concurrency_version >= 1",
    )
    op.create_check_constraint(
        "ck_system_components_concurrency_version",
        "system_components",
        "concurrency_version >= 1",
    )
    op.alter_column("information_systems", "concurrency_version", server_default=None)
    op.alter_column("system_components", "concurrency_version", server_default=None)


def downgrade() -> None:
    op.drop_constraint(
        "ck_system_components_concurrency_version",
        "system_components",
        type_="check",
    )
    op.drop_constraint(
        "ck_information_systems_concurrency_version",
        "information_systems",
        type_="check",
    )
    op.drop_column("system_components", "concurrency_version")
    op.drop_column("information_systems", "concurrency_version")


