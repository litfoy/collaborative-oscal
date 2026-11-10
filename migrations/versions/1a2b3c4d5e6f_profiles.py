"""add tenant-scoped OSCAL profiles

Revision ID: 1a2b3c4d5e6f
Revises: c3b7d1e5a902
Create Date: 2026-11-10

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "1a2b3c4d5e6f"
down_revision: str | Sequence[str] | None = "c3b7d1e5a902"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("catalog_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("document", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "catalog_id", "revision_id"],
            [
                "catalog_revisions.tenant_id",
                "catalog_revisions.catalog_id",
                "catalog_revisions.id",
            ],
            name="fk_profiles_source_revision_same_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_profiles_tenant_id"),
    )
    op.create_index(
        "ix_profiles_tenant_created",
        "profiles",
        ["tenant_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_profiles_tenant_created", table_name="profiles")
    op.drop_table("profiles")
