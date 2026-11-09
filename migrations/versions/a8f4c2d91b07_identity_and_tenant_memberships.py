"""add external identities and tenant memberships

Revision ID: a8f4c2d91b07
Revises: 86d2a7c7b5e1
Create Date: 2026-11-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a8f4c2d91b07"
down_revision: str | Sequence[str] | None = "86d2a7c7b5e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_identities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("issuer", sa.String(length=2048), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("issuer", "subject", name="uq_user_identities_issuer_subject"),
    )
    op.create_table(
        "tenant_memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('tenant_admin', 'catalog_editor', 'viewer')",
            name="ck_tenant_memberships_role",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'inactive')",
            name="ck_tenant_memberships_status",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_tenant_memberships_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user_identities.id"],
            name="fk_tenant_memberships_user_id_user_identities",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "user_id",
            name="uq_tenant_memberships_tenant_user",
        ),
    )
    op.create_index("ix_tenant_memberships_user", "tenant_memberships", ["user_id"])
    op.create_index(
        "ix_tenant_memberships_tenant_status",
        "tenant_memberships",
        ["tenant_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_tenant_memberships_tenant_status", table_name="tenant_memberships")
    op.drop_index("ix_tenant_memberships_user", table_name="tenant_memberships")
    op.drop_table("tenant_memberships")
    op.drop_table("user_identities")
