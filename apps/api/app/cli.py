import argparse
import logging
from pathlib import Path
from uuid import UUID

from app.application.catalog_import import (
    CatalogImportMetadata,
    CatalogImportResult,
    CatalogImportService,
    CatalogImportValidationError,
)
from app.application.identity import IdentityService
from app.application.services import GrcService
from app.config import get_settings
from app.domain.errors import EntityNotFoundError
from app.persistence.database import create_session_factory, create_unit_of_work_factory
from app.persistence.identity import SQLIdentityRepository, SQLMembershipRepository
from app.persistence.models import TenantRecord

logger = logging.getLogger(__name__)


def _bootstrap_tenant_admin(
    *,
    issuer: str,
    subject: str,
    tenant_id: UUID,
) -> tuple[UUID, UUID]:
    configured_issuer = get_settings().oidc_issuer_url
    if not configured_issuer or issuer != configured_issuer:
        raise ValueError("The issuer must exactly match the configured OIDC_ISSUER_URL.")
    if not subject or len(subject) > 255:
        raise ValueError("The external subject must be between 1 and 255 characters.")

    with create_session_factory().begin() as session:
        if session.get(TenantRecord, tenant_id) is None:
            raise ValueError("The selected tenant does not exist.")
        identity = IdentityService(SQLIdentityRepository(session)).resolve_identity(
            issuer=issuer,
            subject=subject,
            display_name=None,
            email=None,
        )
        membership = SQLMembershipRepository(session).assign(
            tenant_id=tenant_id,
            user_id=identity.id,
            role="tenant_admin",
            status="active",
        )

    logger.info(
        "tenant_admin_membership_bootstrapped tenant_id=%s user_identity_id=%s membership_id=%s",
        tenant_id,
        identity.id,
        membership.id,
        extra={"audit_event": "tenant_admin_membership_bootstrapped"},
    )
    return identity.id, membership.id


def _create_tenant(*, name: str, slug: str) -> UUID:
    return GrcService(create_unit_of_work_factory()).create_tenant(name, slug).id


def _import_catalog(
    *,
    tenant_id: UUID,
    path: Path,
    metadata: CatalogImportMetadata,
    target_catalog_id: UUID | None,
) -> CatalogImportResult:
    # Operator-run local provisioning; uses the same validating service as any import.
    service = CatalogImportService(
        create_unit_of_work_factory(),
        max_input_bytes=get_settings().catalog_import_max_input_bytes,
    )
    return service.import_catalog(
        tenant_id,
        path.read_bytes(),
        metadata=metadata,
        target_catalog_id=target_catalog_id,
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    bootstrap = commands.add_parser(
        "bootstrap-admin",
        help="Assign an OIDC identity the tenant-admin role for one existing tenant.",
    )
    bootstrap.add_argument("--issuer", required=True)
    bootstrap.add_argument("--subject", required=True)
    bootstrap.add_argument("--tenant-id", required=True, type=UUID)
    tenant = commands.add_parser("create-tenant", help="Create a tenant for local development.")
    tenant.add_argument("--name", required=True)
    tenant.add_argument("--slug", required=True)
    importer = commands.add_parser(
        "import-catalog",
        help=(
            "Validate and import an OSCAL 1.1.3 or 1.2.1 catalog file "
            "(JSON or YAML) into a tenant."
        ),
    )
    importer.add_argument("--tenant-id", required=True, type=UUID)
    importer.add_argument("--file", required=True, type=Path)
    importer.add_argument("--catalog-id", type=UUID, help="Add a revision to this catalog.")
    importer.add_argument("--catalog-name")
    importer.add_argument("--source-uri")
    importer.add_argument("--source-organization")
    importer.add_argument("--license-identifier")
    arguments = parser.parse_args()

    if arguments.command == "bootstrap-admin":
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        try:
            identity_id, membership_id = _bootstrap_tenant_admin(
                issuer=arguments.issuer,
                subject=arguments.subject,
                tenant_id=arguments.tenant_id,
            )
        except ValueError as exc:
            parser.error(str(exc))
        print(f"Identity {identity_id} assigned tenant-admin membership {membership_id}.")
    elif arguments.command == "create-tenant":
        try:
            tenant_id = _create_tenant(name=arguments.name, slug=arguments.slug)
        except Exception as exc:  # noqa: BLE001 - report operator-facing failure
            parser.error(f"Tenant could not be created: {exc.__class__.__name__}")
        print(f"Tenant {tenant_id} created.")
    elif arguments.command == "import-catalog":
        try:
            result = _import_catalog(
                tenant_id=arguments.tenant_id,
                path=arguments.file,
                metadata=CatalogImportMetadata(
                    source_uri=arguments.source_uri,
                    source_organization=arguments.source_organization,
                    license_identifier=arguments.license_identifier,
                    catalog_name=arguments.catalog_name,
                ),
                target_catalog_id=arguments.catalog_id,
            )
        except CatalogImportValidationError as exc:
            for error in exc.result.errors:
                print(f"error: {error.code} {error.path or '-'}: {error.message}")
            parser.exit(1, "Catalog validation failed.\n")
        except (EntityNotFoundError, OSError, ValueError) as exc:
            parser.error(str(exc))
        outcome = "created" if result.created else "already present"
        print(
            f"Catalog {result.catalog.id} revision {result.revision.id} "
            f"(#{result.revision.revision_number}, {result.control_count} controls) {outcome}."
        )


if __name__ == "__main__":
    main()
