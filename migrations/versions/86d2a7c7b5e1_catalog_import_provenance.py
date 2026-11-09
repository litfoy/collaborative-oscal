"""record catalog import format and prevent duplicate catalog revisions

Revision ID: 86d2a7c7b5e1
Revises: 2fbd279e140e
Create Date: 2026-11-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "86d2a7c7b5e1"
down_revision: str | Sequence[str] | None = "2fbd279e140e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "catalog_revisions",
        sa.Column("source_format", sa.String(length=16), nullable=True),
    )
    op.create_check_constraint(
        "ck_catalog_revisions_source_format",
        "catalog_revisions",
        "source_format IS NULL OR source_format IN ('json', 'yaml')",
    )
    op.create_index(
        "uq_catalog_revisions_catalog_digest",
        "catalog_revisions",
        ["tenant_id", "catalog_id", "content_sha256"],
        unique=True,
        postgresql_where=sa.text("source_format IS NOT NULL"),
    )


def downgrade() -> None:
    connection = op.get_bind()
    existing_constraints = {
        constraint["name"]
        for constraint in sa.inspect(connection).get_unique_constraints("catalog_revisions")
    }
    if "uq_catalog_revisions_catalog_digest" in existing_constraints:
        op.drop_constraint(
            "uq_catalog_revisions_catalog_digest",
            "catalog_revisions",
            type_="unique",
        )
    else:
        existing_indexes = {
            index["name"] for index in sa.inspect(connection).get_indexes("catalog_revisions")
        }
        if "uq_catalog_revisions_catalog_digest" in existing_indexes:
            op.drop_index("uq_catalog_revisions_catalog_digest", table_name="catalog_revisions")
    existing_checks = {
        constraint["name"]
        for constraint in sa.inspect(connection).get_check_constraints("catalog_revisions")
    }
    if "ck_catalog_revisions_source_format" in existing_checks:
        op.drop_constraint(
            "ck_catalog_revisions_source_format",
            "catalog_revisions",
            type_="check",
        )
    op.drop_column("catalog_revisions", "source_format")
