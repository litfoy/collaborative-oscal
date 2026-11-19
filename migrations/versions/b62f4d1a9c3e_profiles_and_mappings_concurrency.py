# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

"""Add optimistic concurrency versions to profiles and mapping collections.

Revision ID: b62f4d1a9c3e
Revises: a91f6c2d4e8b
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b62f4d1a9c3e"
down_revision: str | Sequence[str] | None = "a91f6c2d4e8b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "profiles",
        sa.Column("concurrency_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_check_constraint(
        "ck_profiles_concurrency_version",
        "profiles",
        "concurrency_version >= 1",
    )
    op.alter_column("profiles", "concurrency_version", server_default=None)

    op.add_column(
        "mapping_collections",
        sa.Column("concurrency_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_check_constraint(
        "ck_mapping_collections_concurrency_version",
        "mapping_collections",
        "concurrency_version >= 1",
    )
    op.alter_column("mapping_collections", "concurrency_version", server_default=None)


def downgrade() -> None:
    op.drop_constraint(
        "ck_mapping_collections_concurrency_version",
        "mapping_collections",
        type_="check",
    )
    op.drop_column("mapping_collections", "concurrency_version")

    op.drop_constraint(
        "ck_profiles_concurrency_version",
        "profiles",
        type_="check",
    )
    op.drop_column("profiles", "concurrency_version")

