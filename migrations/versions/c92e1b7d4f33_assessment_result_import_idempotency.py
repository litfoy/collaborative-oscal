# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

"""add assessment result import provenance and idempotency identity

Revision ID: c92e1b7d4f33
Revises: b62f4d1a9c3e
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c92e1b7d4f33"
down_revision: str | Sequence[str] | None = "b62f4d1a9c3e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "assessment_results",
        sa.Column("source_document_uuid", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "assessment_results",
        sa.Column("source_content_sha256", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "assessment_results",
        sa.Column("source_provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_check_constraint(
        "ck_assessment_results_source_content_sha256_format",
        "assessment_results",
        "source_content_sha256 IS NULL OR source_content_sha256 ~ '^[0-9a-f]{64}$'",
    )
    op.create_check_constraint(
        "ck_assessment_results_source_import_completeness",
        "assessment_results",
        "(source_document_uuid IS NULL AND source_content_sha256 IS NULL AND source_provenance IS NULL) OR "
        "(source_document_uuid IS NOT NULL AND source_content_sha256 IS NOT NULL AND source_provenance IS NOT NULL)",
    )
    op.create_index(
        "uq_assessment_results_source_document_uuid",
        "assessment_results",
        ["tenant_id", "source_document_uuid"],
        unique=True,
        postgresql_where=sa.text("source_document_uuid IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_assessment_results_source_document_uuid", table_name="assessment_results")
    op.drop_constraint(
        "ck_assessment_results_source_import_completeness",
        "assessment_results",
        type_="check",
    )
    op.drop_constraint(
        "ck_assessment_results_source_content_sha256_format",
        "assessment_results",
        type_="check",
    )
    op.drop_column("assessment_results", "source_provenance")
    op.drop_column("assessment_results", "source_content_sha256")
    op.drop_column("assessment_results", "source_document_uuid")

