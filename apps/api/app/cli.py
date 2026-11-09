import argparse
import logging
from uuid import UUID

from app.application.identity import IdentityService
from app.config import get_settings
from app.persistence.database import create_session_factory
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


if __name__ == "__main__":
    main()
