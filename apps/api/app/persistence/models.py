from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
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


class DemoSeedRunRecord(Base):
    __tablename__ = "demo_seed_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_demo_seed_runs_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        Index("ix_demo_seed_runs_tenant_applied", "tenant_id", "applied_at"),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    seed_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


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
        Index(
            "ix_group_indexes_revision_parent",
            "tenant_id",
            "catalog_revision_id",
            "parent_group_id",
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
        Index(
            "ix_control_indexes_revision_parent",
            "tenant_id",
            "catalog_revision_id",
            "parent_control_id",
            "display_order",
        ),
        Index(
            "ix_control_indexes_revision_group",
            "tenant_id",
            "catalog_revision_id",
            "group_id",
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


class ProfileRecord(Base):
    __tablename__ = "profiles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_profiles_tenant_id"),
        Index("ix_profiles_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    document: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    concurrency_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __mapper_args__ = {"version_id_col": concurrency_version}


class ProfileImportRecord(Base):
    __tablename__ = "profile_imports"
    __table_args__ = (
        UniqueConstraint("tenant_id", "profile_id", "id", name="uq_profile_import_identity"),
        UniqueConstraint(
            "tenant_id",
            "profile_id",
            "id",
            "catalog_id",
            "revision_id",
            name="uq_profile_import_source",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "profile_id"],
            ["profiles.tenant_id", "profiles.id"],
            name="fk_profile_import_profile",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "catalog_id", "revision_id"],
            ["catalog_revisions.tenant_id", "catalog_revisions.catalog_id", "catalog_revisions.id"],
            name="fk_profile_import_revision",
            ondelete="RESTRICT",
        ),
        CheckConstraint("position >= 0", name="ck_profile_import_position"),
        Index("ix_profile_imports_profile", "tenant_id", "profile_id"),
        Index("ix_profile_imports_revision", "tenant_id", "revision_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    profile_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    catalog_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    revision_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(nullable=False)


class MappingCollectionRecord(Base):
    __tablename__ = "mapping_collections"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_mapping_collections_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_mapping_collections_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(["created_by"], ["user_identities.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["updated_by"], ["user_identities.id"], ondelete="RESTRICT"),
        Index("ix_mapping_collections_tenant_updated", "tenant_id", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    document: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    updated_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    concurrency_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __mapper_args__ = {"version_id_col": concurrency_version}


class MappingMemberRecord(Base):
    __tablename__ = "mapping_members"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "collection_id"],
            ["mapping_collections.tenant_id", "mapping_collections.id"],
            name="fk_mapping_members_collection",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "catalog_id", "revision_id"],
            ["catalog_revisions.tenant_id", "catalog_revisions.catalog_id", "catalog_revisions.id"],
            name="fk_mapping_members_revision",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "revision_id", "control_id"],
            [
                "catalog_control_indexes.tenant_id",
                "catalog_control_indexes.catalog_revision_id",
                "catalog_control_indexes.oscal_control_id",
            ],
            name="fk_mapping_members_control",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "side IN ('source', 'target')",
            name="ck_mapping_members_side",
        ),
        CheckConstraint(
            "(member_type = 'control' AND control_id = oscal_member_id) OR "
            "(member_type = 'statement' AND control_id IS NULL)",
            name="ck_mapping_members_member_type",
        ),
        Index(
            "ix_mapping_members_related_control",
            "tenant_id",
            "revision_id",
            "member_type",
            "oscal_member_id",
        ),
        Index(
            "ix_mapping_members_entry",
            "tenant_id",
            "collection_id",
            "mapping_uuid",
            "entry_uuid",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    collection_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    mapping_uuid: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    entry_uuid: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    member_type: Mapped[str] = mapped_column(String(16), nullable=False)
    catalog_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    revision_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    oscal_member_id: Mapped[str] = mapped_column(String(255), nullable=False)
    control_id: Mapped[str | None] = mapped_column(String(255))


class ControlImplementationRecord(Base):
    __tablename__ = "control_implementations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_implementations_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "id",
            "system_id",
            "system_component_id",
            "catalog_id",
            "revision_id",
            "oscal_control_id",
            name="uq_implementations_ssp_association",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "catalog_id", "revision_id"],
            ["catalog_revisions.tenant_id", "catalog_revisions.catalog_id", "catalog_revisions.id"],
            name="fk_implementations_revision",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "revision_id", "oscal_control_id"],
            [
                "catalog_control_indexes.tenant_id",
                "catalog_control_indexes.catalog_revision_id",
                "catalog_control_indexes.oscal_control_id",
            ],
            name="fk_implementations_control",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "organization_id"],
            ["organizations.tenant_id", "organizations.id"],
            name="fk_implementations_organization",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "system_id"],
            ["information_systems.tenant_id", "information_systems.id"],
            name="fk_implementations_system",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "system_id", "system_component_id"],
            [
                "system_components.tenant_id",
                "system_components.system_id",
                "system_components.id",
            ],
            name="fk_implementations_system_component",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "profile_id"],
            ["profiles.tenant_id", "profiles.id"],
            name="fk_implementations_profile",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "profile_id", "profile_import_id", "catalog_id", "revision_id"],
            [
                "profile_imports.tenant_id",
                "profile_imports.profile_id",
                "profile_imports.id",
                "profile_imports.catalog_id",
                "profile_imports.revision_id",
            ],
            name="fk_implementations_profile_import",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "profile_import_id IS NULL OR profile_id IS NOT NULL",
            name="ck_implementation_import_profile",
        ),
        CheckConstraint(
            "system_component_id IS NULL OR system_id IS NOT NULL",
            name="ck_implementation_component_requires_system",
        ),
        CheckConstraint(
            "oscal_implementation_status IS NULL OR oscal_implementation_status IN "
            "('implemented', 'partial', 'planned', 'alternative', 'not-applicable')",
            name="ck_implementation_oscal_status",
        ),
        CheckConstraint(
            "oscal_implementation_status NOT IN ('planned', 'alternative', 'not-applicable') "
            "OR coalesce(length(trim(oscal_status_explanation)), 0) > 0",
            name="ck_implementation_oscal_status_explanation",
        ),
        CheckConstraint(
            "oscal_implementation_status IS NOT NULL OR oscal_status_explanation IS NULL",
            name="ck_implementation_oscal_explanation_requires_status",
        ),
        ForeignKeyConstraint(["created_by"], ["user_identities.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["updated_by"], ["user_identities.id"], ondelete="RESTRICT"),
        CheckConstraint(
            "status IN ('not_started', 'in_progress', 'implemented', 'not_applicable')",
            name="ck_implementations_status",
        ),
        Index("ix_implementations_tenant_profile", "tenant_id", "profile_id"),
        Index("ix_implementations_tenant_organization", "tenant_id", "organization_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    organization_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    system_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    system_component_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    profile_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    profile_import_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    catalog_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    revision_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    oscal_control_id: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    oscal_implementation_status: Mapped[str | None] = mapped_column(String(32))
    oscal_status_explanation: Mapped[str | None] = mapped_column(Text)
    evidence_references: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    updated_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ImplementationResponsibilityRecord(Base):
    __tablename__ = "implementation_responsibilities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "implementation_id"],
            ["control_implementations.tenant_id", "control_implementations.id"],
            name="fk_responsibilities_implementation",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.user_id"],
            name="fk_responsibilities_membership",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "kind IN ('accountable', 'responsible', 'participant')",
            name="ck_responsibilities_kind",
        ),
        UniqueConstraint(
            "implementation_id",
            "kind",
            "user_id",
            "role",
            name="uq_implementation_responsibility",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    implementation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    role: Mapped[str] = mapped_column(String(255), nullable=False)


class ComponentDefinitionRecord(Base):
    __tablename__ = "component_definitions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_component_definitions_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_component_definitions_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(["created_by"], ["user_identities.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["updated_by"], ["user_identities.id"], ondelete="RESTRICT"),
        Index("ix_component_definitions_tenant_updated", "tenant_id", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    document: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    updated_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ComponentDefinitionComponentRecord(Base):
    __tablename__ = "component_definition_components"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "document_id", "id", name="uq_component_definition_component_identity"
        ),
        UniqueConstraint(
            "tenant_id",
            "document_id",
            "oscal_component_uuid",
            name="uq_component_definition_component_oscal_uuid",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["component_definitions.tenant_id", "component_definitions.id"],
            name="fk_component_definition_component_document",
            ondelete="CASCADE",
        ),
        Index("ix_component_definition_components_document", "tenant_id", "document_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    document_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    oscal_component_uuid: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)


class ComponentDefinitionSourceRecord(Base):
    __tablename__ = "component_definition_sources"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "component_id",
            "control_implementation_uuid",
            "implemented_requirement_uuid",
            name="uq_component_definition_source_requirement",
        ),
        UniqueConstraint(
            "tenant_id",
            "component_id",
            "catalog_id",
            "revision_id",
            "oscal_control_id",
            name="uq_component_definition_source_control",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "document_id", "component_id"],
            [
                "component_definition_components.tenant_id",
                "component_definition_components.document_id",
                "component_definition_components.id",
            ],
            name="fk_component_definition_source_component",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "catalog_id", "revision_id"],
            [
                "catalog_revisions.tenant_id",
                "catalog_revisions.catalog_id",
                "catalog_revisions.id",
            ],
            name="fk_component_definition_source_revision",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "revision_id", "oscal_control_id"],
            [
                "catalog_control_indexes.tenant_id",
                "catalog_control_indexes.catalog_revision_id",
                "catalog_control_indexes.oscal_control_id",
            ],
            name="fk_component_definition_source_control",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_component_definition_sources_control",
            "tenant_id",
            "catalog_id",
            "revision_id",
            "oscal_control_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    document_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    component_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    control_implementation_uuid: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    implemented_requirement_uuid: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    catalog_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    revision_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    oscal_control_id: Mapped[str] = mapped_column(String(255), nullable=False)


class InformationSystemRecord(Base):
    __tablename__ = "information_systems"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_information_systems_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_information_systems_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "organization_id"],
            ["organizations.tenant_id", "organizations.id"],
            name="fk_information_systems_organization",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["created_by"],
            ["user_identities.id"],
            name="fk_information_systems_created_by",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["updated_by"],
            ["user_identities.id"],
            name="fk_information_systems_updated_by",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "operational_status IS NULL OR operational_status IN "
            "('operational', 'under-development', 'under-major-modification', "
            "'disposition', 'other')",
            name="ck_information_systems_status",
        ),
        CheckConstraint(
            "operational_status != 'other' OR coalesce(length(trim(status_remarks)), 0) > 0",
            name="ck_information_systems_other_status_remarks",
        ),
        Index("ix_information_systems_tenant_updated", "tenant_id", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    organization_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    system_boundary: Mapped[str | None] = mapped_column(Text)
    system_ids: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    information_types: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    operational_status: Mapped[str | None] = mapped_column(String(32))
    status_remarks: Mapped[str | None] = mapped_column(Text)
    security_sensitivity_level: Mapped[str | None] = mapped_column(String(255))
    created_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    updated_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ComponentDefinitionSnapshotRecord(Base):
    __tablename__ = "component_definition_snapshots"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_component_definition_snapshots_tenant_id"),
        UniqueConstraint(
            "tenant_id", "content_sha256", name="uq_component_definition_snapshots_digest"
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_component_definition_snapshots_tenant",
            ondelete="RESTRICT",
        ),
        Index("ix_component_definition_snapshots_created", "tenant_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    source_document_uuid: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    document: Mapped[dict] = mapped_column(JSONB, nullable=False)
    diagnostics: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SystemComponentRecord(Base):
    __tablename__ = "system_components"
    __table_args__ = (
        UniqueConstraint("tenant_id", "system_id", "id", name="uq_system_components_identity"),
        UniqueConstraint(
            "tenant_id", "system_id", "oscal_component_uuid", name="uq_system_components_oscal_uuid"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "system_id"],
            ["information_systems.tenant_id", "information_systems.id"],
            name="fk_system_components_system",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "source_snapshot_id"],
            ["component_definition_snapshots.tenant_id", "component_definition_snapshots.id"],
            name="fk_system_components_source_snapshot",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["created_by"],
            ["user_identities.id"],
            name="fk_system_components_created_by",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["updated_by"],
            ["user_identities.id"],
            name="fk_system_components_updated_by",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(source_snapshot_id IS NULL AND source_component_uuid IS NULL) OR "
            "(source_snapshot_id IS NOT NULL AND source_component_uuid IS NOT NULL)",
            name="ck_system_components_source_identity",
        ),
        Index("ix_system_components_system_created", "tenant_id", "system_id", "created_at"),
        Index(
            "uq_system_components_this_system",
            "tenant_id",
            "system_id",
            unique=True,
            postgresql_where=text("is_system_component"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    system_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    oscal_component_uuid: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    source_snapshot_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    source_component_uuid: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    is_system_component: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    component: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    updated_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SystemSecurityPlanRecord(Base):
    __tablename__ = "system_security_plans"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_system_security_plans_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "id",
            "system_id",
            "catalog_id",
            "revision_id",
            name="uq_system_security_plans_context",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "system_id"],
            ["information_systems.tenant_id", "information_systems.id"],
            name="fk_system_security_plans_system",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "catalog_id", "revision_id"],
            ["catalog_revisions.tenant_id", "catalog_revisions.catalog_id", "catalog_revisions.id"],
            name="fk_system_security_plans_baseline",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["created_by"],
            ["user_identities.id"],
            name="fk_system_security_plans_created_by",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["updated_by"],
            ["user_identities.id"],
            name="fk_system_security_plans_updated_by",
            ondelete="RESTRICT",
        ),
        Index("ix_system_security_plans_system_updated", "tenant_id", "system_id", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    system_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    catalog_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    revision_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    control_implementation_description: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    updated_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    concurrency_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __mapper_args__ = {"version_id_col": concurrency_version}


class SystemSecurityPlanVersionRecord(Base):
    __tablename__ = "system_security_plan_versions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_system_security_plan_versions_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "id",
            "system_security_plan_id",
            name="uq_system_security_plan_versions_identity",
        ),
        UniqueConstraint(
            "tenant_id",
            "system_security_plan_id",
            "content_sha256",
            name="uq_system_security_plan_versions_digest",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "system_security_plan_id"],
            ["system_security_plans.tenant_id", "system_security_plans.id"],
            name="fk_system_security_plan_versions_plan",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "catalog_id", "revision_id"],
            ["catalog_revisions.tenant_id", "catalog_revisions.catalog_id", "catalog_revisions.id"],
            name="fk_system_security_plan_versions_baseline",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_system_security_plan_versions_plan_created",
            "tenant_id",
            "system_security_plan_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    system_security_plan_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    catalog_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    revision_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    oscal_document_uuid: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    oscal_version: Mapped[str] = mapped_column(String(32), nullable=False)
    document_version: Mapped[str] = mapped_column(String(64), nullable=False)
    last_modified: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    document: Mapped[dict] = mapped_column(JSONB, nullable=False)
    diagnostics: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AssessmentPlanRecord(Base):
    __tablename__ = "assessment_plans"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_assessment_plans_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "id",
            "system_id",
            "system_security_plan_id",
            "system_security_plan_version_id",
            name="uq_assessment_plans_context",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "system_id"],
            ["information_systems.tenant_id", "information_systems.id"],
            name="fk_assessment_plans_system",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "system_security_plan_id"],
            ["system_security_plans.tenant_id", "system_security_plans.id"],
            name="fk_assessment_plans_ssp",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "system_security_plan_version_id"],
            ["system_security_plan_versions.tenant_id", "system_security_plan_versions.id"],
            name="fk_assessment_plans_ssp_version",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["created_by"],
            ["user_identities.id"],
            name="fk_assessment_plans_created_by",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["updated_by"],
            ["user_identities.id"],
            name="fk_assessment_plans_updated_by",
            ondelete="RESTRICT",
        ),
        Index("ix_assessment_plans_system_updated", "tenant_id", "system_id", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    system_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    system_security_plan_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    system_security_plan_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    working_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    updated_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    concurrency_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __mapper_args__ = {"version_id_col": concurrency_version}


class AssessmentPlanVersionRecord(Base):
    __tablename__ = "assessment_plan_versions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_assessment_plan_versions_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "id",
            "assessment_plan_id",
            name="uq_assessment_plan_versions_identity",
        ),
        UniqueConstraint(
            "tenant_id",
            "assessment_plan_id",
            "content_sha256",
            name="uq_assessment_plan_versions_digest",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "assessment_plan_id"],
            ["assessment_plans.tenant_id", "assessment_plans.id"],
            name="fk_assessment_plan_versions_plan",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "system_security_plan_version_id"],
            ["system_security_plan_versions.tenant_id", "system_security_plan_versions.id"],
            name="fk_assessment_plan_versions_ssp_version",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_assessment_plan_versions_plan_created",
            "tenant_id",
            "assessment_plan_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    assessment_plan_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    system_security_plan_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )
    oscal_document_uuid: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    oscal_version: Mapped[str] = mapped_column(String(32), nullable=False)
    document_version: Mapped[str] = mapped_column(String(64), nullable=False)
    last_modified: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    document: Mapped[dict] = mapped_column(JSONB, nullable=False)
    diagnostics: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AssessmentResultRecord(Base):
    __tablename__ = "assessment_results"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_assessment_results_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "id",
            "system_id",
            "assessment_plan_id",
            "assessment_plan_version_id",
            name="uq_assessment_results_context",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "system_id"],
            ["information_systems.tenant_id", "information_systems.id"],
            name="fk_assessment_results_system",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "assessment_plan_id"],
            ["assessment_plans.tenant_id", "assessment_plans.id"],
            name="fk_assessment_results_plan",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "assessment_plan_version_id"],
            ["assessment_plan_versions.tenant_id", "assessment_plan_versions.id"],
            name="fk_assessment_results_plan_version",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["created_by"],
            ["user_identities.id"],
            name="fk_assessment_results_created_by",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["updated_by"],
            ["user_identities.id"],
            name="fk_assessment_results_updated_by",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_assessment_results_system_updated",
            "tenant_id",
            "system_id",
            "updated_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    system_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    assessment_plan_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    assessment_plan_version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    working_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    updated_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    concurrency_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __mapper_args__ = {"version_id_col": concurrency_version}


class AssessmentResultVersionRecord(Base):
    __tablename__ = "assessment_result_versions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_assessment_result_versions_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "id",
            "assessment_result_id",
            name="uq_assessment_result_versions_identity",
        ),
        UniqueConstraint(
            "tenant_id",
            "assessment_result_id",
            "content_sha256",
            name="uq_assessment_result_versions_digest",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "assessment_result_id"],
            ["assessment_results.tenant_id", "assessment_results.id"],
            name="fk_assessment_result_versions_result",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "assessment_plan_version_id"],
            ["assessment_plan_versions.tenant_id", "assessment_plan_versions.id"],
            name="fk_assessment_result_versions_plan_version",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_assessment_result_versions_result_created",
            "tenant_id",
            "assessment_result_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    assessment_result_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    assessment_plan_version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    oscal_document_uuid: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    oscal_version: Mapped[str] = mapped_column(String(32), nullable=False)
    document_version: Mapped[str] = mapped_column(String(64), nullable=False)
    last_modified: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    document: Mapped[dict] = mapped_column(JSONB, nullable=False)
    diagnostics: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SystemSecurityPlanImplementationRecord(Base):
    __tablename__ = "system_security_plan_implementations"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "system_security_plan_id",
            "implementation_id",
            name="uq_system_security_plan_implementation",
        ),
        UniqueConstraint(
            "tenant_id",
            "system_security_plan_id",
            "oscal_control_id",
            "system_component_id",
            name="uq_system_security_plan_component_contribution",
        ),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "system_security_plan_id",
                "system_id",
                "catalog_id",
                "revision_id",
            ],
            [
                "system_security_plans.tenant_id",
                "system_security_plans.id",
                "system_security_plans.system_id",
                "system_security_plans.catalog_id",
                "system_security_plans.revision_id",
            ],
            name="fk_system_security_plan_implementations_plan_context",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "implementation_id",
                "system_id",
                "system_component_id",
                "catalog_id",
                "revision_id",
                "oscal_control_id",
            ],
            [
                "control_implementations.tenant_id",
                "control_implementations.id",
                "control_implementations.system_id",
                "control_implementations.system_component_id",
                "control_implementations.catalog_id",
                "control_implementations.revision_id",
                "control_implementations.oscal_control_id",
            ],
            name="fk_system_security_plan_implementations_record",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "system_id", "system_component_id"],
            [
                "system_components.tenant_id",
                "system_components.system_id",
                "system_components.id",
            ],
            name="fk_system_security_plan_implementations_component",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "revision_id", "oscal_control_id"],
            [
                "catalog_control_indexes.tenant_id",
                "catalog_control_indexes.catalog_revision_id",
                "catalog_control_indexes.oscal_control_id",
            ],
            name="fk_system_security_plan_implementations_control",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_system_security_plan_implementations_plan",
            "tenant_id",
            "system_security_plan_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    system_security_plan_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    implementation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    system_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    system_component_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    catalog_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    revision_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    oscal_control_id: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
