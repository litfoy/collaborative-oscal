from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TenantRecord(Base):
    __tablename__ = "tenants"
    __table_args__ = (UniqueConstraint("slug", name="uq_tenants_slug"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UserIdentityRecord(Base):
    __tablename__ = "user_identities"
    __table_args__ = (
        UniqueConstraint("issuer", "subject", name="uq_user_identities_issuer_subject"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    issuer: Mapped[str] = mapped_column(String(2048), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TenantMembershipRecord(Base):
    __tablename__ = "tenant_memberships"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_tenant_memberships_tenant_user"),
        CheckConstraint(
            "role IN ('tenant_admin', 'catalog_editor', 'viewer')",
            name="ck_tenant_memberships_role",
        ),
        CheckConstraint(
            "status IN ('active', 'inactive')",
            name="ck_tenant_memberships_status",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_tenant_memberships_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["user_id"],
            ["user_identities.id"],
            name="fk_tenant_memberships_user_id_user_identities",
            ondelete="CASCADE",
        ),
        Index("ix_tenant_memberships_user", "user_id"),
        Index("ix_tenant_memberships_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OrganizationRecord(Base):
    __tablename__ = "organizations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_organizations_tenant_id"),
        UniqueConstraint("tenant_id", "slug", name="uq_organizations_tenant_slug"),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_organizations_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "parent_organization_id"],
            ["organizations.tenant_id", "organizations.id"],
            name="fk_organizations_parent_same_tenant",
            ondelete="RESTRICT",
        ),
        Index("ix_organizations_tenant_parent", "tenant_id", "parent_organization_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    parent_organization_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CatalogRecord(Base):
    __tablename__ = "catalogs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_catalogs_tenant_id"),
        CheckConstraint(
            "origin_type IN ('imported', 'custom')",
            name="ck_catalogs_origin_type",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_catalogs_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        Index("ix_catalogs_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    origin_type: Mapped[str] = mapped_column(String(16), nullable=False)
    source_uri: Mapped[str | None] = mapped_column(Text)
    source_organization: Mapped[str | None] = mapped_column(String(255))
    license_identifier: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CatalogRevisionRecord(Base):
    __tablename__ = "catalog_revisions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_catalog_revisions_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "catalog_id",
            "revision_number",
            name="uq_catalog_revisions_tenant_catalog_number",
        ),
        UniqueConstraint(
            "tenant_id",
            "catalog_id",
            "id",
            name="uq_catalog_revisions_tenant_catalog_id",
        ),
        Index(
            "uq_catalog_revisions_catalog_digest",
            "tenant_id",
            "catalog_id",
            "content_sha256",
            unique=True,
            postgresql_where=text("source_format IS NOT NULL"),
        ),
        ForeignKeyConstraint(
            ["tenant_id", "catalog_id"],
            ["catalogs.tenant_id", "catalogs.id"],
            name="fk_catalog_revisions_catalog_same_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint("revision_number > 0", name="ck_catalog_revisions_positive_number"),
        CheckConstraint(
            "source_format IS NULL OR source_format IN ('json', 'yaml')",
            name="ck_catalog_revisions_source_format",
        ),
        CheckConstraint(
            "content_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_catalog_revisions_sha256_format",
        ),
        CheckConstraint(
            "(lifecycle_status = 'draft' AND published_at IS NULL) OR "
            "(lifecycle_status = 'published' AND published_at IS NOT NULL)",
            name="ck_catalog_revisions_published_at",
        ),
        Index("ix_catalog_revisions_tenant_catalog", "tenant_id", "catalog_id"),
        Index("ix_catalog_revisions_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    catalog_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(String(16), nullable=False)
    oscal_document_uuid: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    oscal_version: Mapped[str] = mapped_column(String(32), nullable=False)
    source_version: Mapped[str | None] = mapped_column(String(255))
    source_format: Mapped[str | None] = mapped_column(String(16))
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CatalogGroupIndexRecord(Base):
    __tablename__ = "catalog_group_indexes"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "catalog_revision_id",
            "id",
            name="uq_group_indexes_scope_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "catalog_revision_id",
            "structural_path",
            name="uq_group_indexes_revision_path",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "catalog_revision_id"],
            ["catalog_revisions.tenant_id", "catalog_revisions.id"],
            name="fk_group_indexes_revision_same_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "catalog_revision_id", "parent_group_id"],
            [
                "catalog_group_indexes.tenant_id",
                "catalog_group_indexes.catalog_revision_id",
                "catalog_group_indexes.id",
            ],
            name="fk_group_indexes_parent_same_revision",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_group_indexes_revision_order",
            "tenant_id",
            "catalog_revision_id",
            "display_order",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    catalog_revision_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    oscal_group_id: Mapped[str | None] = mapped_column(String(255))
    parent_group_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    structural_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)


class CatalogControlIndexRecord(Base):
    __tablename__ = "catalog_control_indexes"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "catalog_revision_id",
            "id",
            name="uq_control_indexes_scope_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "catalog_revision_id",
            "oscal_control_id",
            name="uq_control_indexes_revision_oscal_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "catalog_revision_id",
            "structural_path",
            name="uq_control_indexes_revision_path",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "catalog_revision_id"],
            ["catalog_revisions.tenant_id", "catalog_revisions.id"],
            name="fk_control_indexes_revision_same_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "catalog_revision_id", "parent_control_id"],
            [
                "catalog_control_indexes.tenant_id",
                "catalog_control_indexes.catalog_revision_id",
                "catalog_control_indexes.id",
            ],
            name="fk_control_indexes_parent_same_revision",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "catalog_revision_id", "group_id"],
            [
                "catalog_group_indexes.tenant_id",
                "catalog_group_indexes.catalog_revision_id",
                "catalog_group_indexes.id",
            ],
            name="fk_control_indexes_group_same_revision",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_control_indexes_revision_order",
            "tenant_id",
            "catalog_revision_id",
            "display_order",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    catalog_revision_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    oscal_control_id: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_control_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    group_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    structural_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)
