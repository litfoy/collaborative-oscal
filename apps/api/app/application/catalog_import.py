from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from collaborative_oscal_oscal.catalog_import import (
    DEFAULT_MAX_INPUT_BYTES,
    CatalogInputFormat,
    CatalogValidationOutcome,
    CatalogValidationResult,
    validate_catalog_bytes,
)
from collaborative_oscal_oscal.catalog_index import canonical_json_sha256

from app.application.catalog_revisions import prepare_catalog_revision
from app.domain.catalogs.models import (
    Catalog,
    CatalogOriginType,
    CatalogRevision,
)
from app.domain.errors import EntityNotFoundError
from app.domain.repositories import UnitOfWork

UnitOfWorkFactory = Callable[[], UnitOfWork]


def _publisher_name(metadata: dict[str, Any]) -> str | None:
    source_parties = metadata.get("parties")
    source_roles = metadata.get("roles")
    responsible_parties = metadata.get("responsible-parties")
    if not isinstance(source_parties, list) or not isinstance(source_roles, list):
        return None
    if not isinstance(responsible_parties, list):
        return None
    parties = {
        party.get("uuid"): party
        for party in source_parties
        if isinstance(party, dict) and isinstance(party.get("uuid"), str)
    }
    roles = {
        role.get("id"): role
        for role in source_roles
        if isinstance(role, dict) and isinstance(role.get("id"), str)
    }
    for responsible_party in responsible_parties:
        if not isinstance(responsible_party, dict):
            continue
        role_id = responsible_party.get("role-id")
        role = roles.get(role_id) if isinstance(role_id, str) else None
        if not (
            isinstance(role_id, str)
            and role_id.casefold() == "publisher"
            or isinstance(role, dict)
            and isinstance(role.get("title"), str)
            and role["title"].casefold() == "publisher"
        ):
            continue
        party_uuids = responsible_party.get("party-uuids")
        if not isinstance(party_uuids, list):
            continue
        for party_id in party_uuids:
            if not isinstance(party_id, str):
                continue
            party = parties.get(party_id)
            if isinstance(party, dict) and isinstance(party.get("name"), str):
                return party["name"]
    return None


@dataclass(frozen=True, slots=True)
class CatalogImportMetadata:
    source_uri: str | None = None
    source_organization: str | None = None
    license_identifier: str | None = None
    catalog_name: str | None = None


@dataclass(frozen=True, slots=True)
class CatalogImportResult:
    catalog: Catalog
    revision: CatalogRevision
    control_count: int
    created: bool


class CatalogImportValidationError(ValueError):
    def __init__(self, result: CatalogValidationResult) -> None:
        super().__init__("Catalog import validation failed.")
        self.result = result


class CatalogImportService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        *,
        max_input_bytes: int = DEFAULT_MAX_INPUT_BYTES,
        max_nesting_depth: int = 64,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._max_input_bytes = max_input_bytes
        self._max_nesting_depth = max_nesting_depth

    def validate_catalog(
        self,
        content: bytes,
        input_format: CatalogInputFormat | str = CatalogInputFormat.AUTO,
    ) -> CatalogValidationOutcome:
        return validate_catalog_bytes(
            content,
            input_format,
            max_input_bytes=self._max_input_bytes,
            max_nesting_depth=self._max_nesting_depth,
        )

    def import_catalog(
        self,
        tenant_id: UUID,
        content: bytes,
        input_format: CatalogInputFormat | str = CatalogInputFormat.AUTO,
        metadata: CatalogImportMetadata = CatalogImportMetadata(),
        target_catalog_id: UUID | None = None,
    ) -> CatalogImportResult:
        outcome = self.validate_catalog(content, input_format)
        if not outcome.result.valid or outcome.document is None or outcome.input_format is None:
            raise CatalogImportValidationError(outcome.result)

        document = outcome.document
        catalog_content = document["catalog"]
        oscal_metadata: dict[str, Any] = catalog_content["metadata"]
        content_sha256 = canonical_json_sha256(document)
        catalog_name = metadata.catalog_name or oscal_metadata["title"]
        if not isinstance(catalog_name, str) or not catalog_name.strip():
            raise ValueError("Catalog name must not be empty.")
        catalog_name = catalog_name.strip()
        source_version = oscal_metadata.get("version")
        if not isinstance(source_version, str):
            source_version = None
        source_organization = metadata.source_organization or _publisher_name(oscal_metadata)

        with self._unit_of_work_factory() as unit_of_work:
            if unit_of_work.tenants.get(tenant_id) is None:
                raise EntityNotFoundError("Tenant not found.")

            if target_catalog_id is None:
                now = datetime.now(UTC)
                catalog = Catalog(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    name=catalog_name,
                    description=None,
                    origin_type=CatalogOriginType.IMPORTED,
                    source_uri=metadata.source_uri,
                    source_organization=source_organization,
                    license_identifier=metadata.license_identifier,
                    created_at=now,
                    updated_at=now,
                )
                unit_of_work.catalogs.add(catalog)
            else:
                catalog = unit_of_work.catalogs.get(tenant_id, target_catalog_id)
                if catalog is None:
                    raise EntityNotFoundError("Catalog not found in this tenant.")

            existing = unit_of_work.revisions.find_by_digest(tenant_id, catalog.id, content_sha256)
            if existing is not None:
                return CatalogImportResult(
                    catalog,
                    existing,
                    len(unit_of_work.revisions.list_controls(tenant_id, existing.id)),
                    False,
                )

            revision_number = unit_of_work.revisions.next_revision_number(tenant_id, catalog.id)
            existing = unit_of_work.revisions.find_by_digest(tenant_id, catalog.id, content_sha256)
            if existing is not None:
                return CatalogImportResult(
                    catalog,
                    existing,
                    len(unit_of_work.revisions.list_controls(tenant_id, existing.id)),
                    False,
                )

            revision, groups, controls = prepare_catalog_revision(
                tenant_id,
                catalog.id,
                revision_number,
                document,
                source_version=source_version,
                source_format=outcome.input_format.value,
            )
            unit_of_work.revisions.add(revision, groups, controls)
            result = CatalogImportResult(catalog, revision, len(controls), True)
        return result
