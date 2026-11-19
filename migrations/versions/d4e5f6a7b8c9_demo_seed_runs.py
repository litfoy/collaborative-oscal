# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

"""Add tenant-scoped demo seed run markers.

Revision ID: d4e5f6a7b8c9
Revises: c5d2f61a8b91
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | Sequence[str] | None = "c5d2f61a8b91"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "demo_seed_runs",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("seed_name", sa.String(length=100), nullable=False),
        sa.Column(
            "applied_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("tenant_id", "seed_name"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_demo_seed_runs_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_demo_seed_runs_tenant_applied",
        "demo_seed_runs",
        ["tenant_id", "applied_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_demo_seed_runs_tenant_applied", table_name="demo_seed_runs")
    op.drop_table("demo_seed_runs")


