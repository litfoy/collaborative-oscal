# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.persistence.models import TenantMembershipRecord, TenantRecord, UserIdentityRecord

DEMO_TENANT_ID = UUID("86713b38-b7f0-4b6a-9c22-4e672d5cc9d4")
DEMO_USER_ID = UUID("860aef82-7f6a-48a5-b319-967dd3da4f95")
DEMO_MEMBERSHIP_ID = UUID("0d3de598-5fb7-43cb-9d0b-f5338a09f647")
DEMO_ISSUER = "urn:collaborative-oscal:demo"
DEMO_SUBJECT = "demo-user"
DEMO_NAME = "Demo User"
DEMO_TENANT_NAME = "Acme Corp"
DEMO_TENANT_SLUG = "collaborative-oscal-demo-acme"


def demo_state_valid(session: Session) -> bool:
    tenant = session.get(TenantRecord, DEMO_TENANT_ID)
    identity = session.get(UserIdentityRecord, DEMO_USER_ID)
    membership = session.scalar(
        select(TenantMembershipRecord).where(
            TenantMembershipRecord.tenant_id == DEMO_TENANT_ID,
            TenantMembershipRecord.user_id == DEMO_USER_ID,
        )
    )
    return bool(
        tenant
        and tenant.name == DEMO_TENANT_NAME
        and tenant.slug == DEMO_TENANT_SLUG
        and identity
        and identity.issuer == DEMO_ISSUER
        and identity.subject == DEMO_SUBJECT
        and identity.display_name == DEMO_NAME
        and identity.email is None
        and membership
        and membership.id == DEMO_MEMBERSHIP_ID
        and membership.role == "catalog_editor"
        and membership.status == "active"
    )
