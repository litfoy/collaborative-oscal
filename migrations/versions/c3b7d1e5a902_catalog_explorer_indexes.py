"""catalog explorer hierarchy indexes

Revision ID: c3b7d1e5a902
Revises: a8f4c2d91b07
Create Date: 2026-11-09 23:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "c3b7d1e5a902"
down_revision: str | Sequence[str] | None = "a8f4c2d91b07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_control_indexes_revision_parent",
        "catalog_control_indexes",
        ["tenant_id", "catalog_revision_id", "parent_control_id", "display_order"],
    )
    op.create_index(
        "ix_control_indexes_revision_group",
        "catalog_control_indexes",
        ["tenant_id", "catalog_revision_id", "group_id", "display_order"],
    )
    op.create_index(
        "ix_group_indexes_revision_parent",
        "catalog_group_indexes",
        ["tenant_id", "catalog_revision_id", "parent_group_id", "display_order"],
    )


def downgrade() -> None:
    op.drop_index("ix_group_indexes_revision_parent", table_name="catalog_group_indexes")
    op.drop_index("ix_control_indexes_revision_group", table_name="catalog_control_indexes")
    op.drop_index("ix_control_indexes_revision_parent", table_name="catalog_control_indexes")
