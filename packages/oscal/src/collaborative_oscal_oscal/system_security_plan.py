# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from jsonschema import Draft7Validator
from jsonschema import ValidationError as JsonSchemaValidationError
from pydantic import ValidationError as PydanticValidationError
from trestle.oscal.ssp import Model as TrestleSystemSecurityPlanModel

from collaborative_oscal_oscal.authoring import (
    OscalAuthoringError,
    serialize_authored_document,
)
from collaborative_oscal_oscal.catalog_import import _OSCAL_DRAFT7_VALIDATOR
from collaborative_oscal_oscal.versions import (
    BUNDLED_JSON_SCHEMA_OSCAL_VERSIONS,
    OscalDocumentModel,
    authoring_version_for,
    is_supported_oscal_version,
    load_oscal_schema,
    uses_trestle_model,
)

DEFAULT_SSP_OSCAL_VERSION = authoring_version_for(
    OscalDocumentModel.SYSTEM_SECURITY_PLAN
)


class SystemSecurityPlanValidationError(ValueError):
    pass


def serialize_authored_system_security_plan(
    document: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        version = document["system-security-plan"]["metadata"]["oscal-version"]
        if uses_trestle_model(OscalDocumentModel.SYSTEM_SECURITY_PLAN, version):
            return serialize_authored_document(
                TrestleSystemSecurityPlanModel,
                document,
                OscalDocumentModel.SYSTEM_SECURITY_PLAN,
                version,
            )
        validate_system_security_plan_document(document)
        return dict(document)
    except OscalAuthoringError as error:
        raise SystemSecurityPlanValidationError(str(error)) from error


def validate_system_security_plan_document(
    document: Mapping[str, Any],
    *,
    baseline_control_ids: set[str] | None = None,
    expected_baseline_href: str | None = None,
) -> None:
    try:
        body = document["system-security-plan"]
        version = body["metadata"]["oscal-version"]
        if not is_supported_oscal_version(
            OscalDocumentModel.SYSTEM_SECURITY_PLAN, version
        ):
            raise SystemSecurityPlanValidationError(
                "Unsupported OSCAL System Security Plan version."
            )
        if uses_trestle_model(OscalDocumentModel.SYSTEM_SECURITY_PLAN, version):
            TrestleSystemSecurityPlanModel.model_validate(document)
        if version not in BUNDLED_JSON_SCHEMA_OSCAL_VERSIONS and not uses_trestle_model(
            OscalDocumentModel.SYSTEM_SECURITY_PLAN, version
        ):
            raise SystemSecurityPlanValidationError(
                "No validator is configured for the declared SSP version."
            )
        if version in BUNDLED_JSON_SCHEMA_OSCAL_VERSIONS:
            _OSCAL_DRAFT7_VALIDATOR(
                load_oscal_schema(OscalDocumentModel.SYSTEM_SECURITY_PLAN, version),
                format_checker=Draft7Validator.FORMAT_CHECKER,
            ).validate(document)
        if (
            expected_baseline_href is not None
            and body["import-profile"]["href"] != expected_baseline_href
        ):
            raise SystemSecurityPlanValidationError(
                "SSP baseline reference does not match the pinned Catalog revision."
            )
        component_uuid_values = [
            UUID(component["uuid"])
            for component in body["system-implementation"]["components"]
        ]
        component_ids = set(component_uuid_values)
        all_subject_ids = [UUID(body["uuid"]), *component_uuid_values]
        all_subject_ids.extend(
            UUID(item["uuid"])
            for item in body["system-characteristics"]["system-information"][
                "information-types"
            ]
            if "uuid" in item
        )
        seen_requirements: set[str] = set()
        for requirement in body["control-implementation"]["implemented-requirements"]:
            all_subject_ids.append(UUID(requirement["uuid"]))
            control_id = requirement["control-id"]
            if (
                baseline_control_ids is not None
                and control_id not in baseline_control_ids
            ):
                raise SystemSecurityPlanValidationError(
                    f"Implemented requirement {control_id!r} is not in the pinned baseline."
                )
            if control_id in seen_requirements:
                raise SystemSecurityPlanValidationError(
                    f"Baseline control {control_id!r} is represented more than once."
                )
            seen_requirements.add(control_id)
            by_component_ids: set[UUID] = set()
            for contribution in requirement.get("by-components", []):
                component_id = UUID(contribution["component-uuid"])
                if component_id not in component_ids:
                    raise SystemSecurityPlanValidationError(
                        f"Contribution references unknown system component {component_id}."
                    )
                if component_id in by_component_ids:
                    raise SystemSecurityPlanValidationError(
                        f"Requirement {control_id!r} has duplicate contributions "
                        "from one component."
                    )
                by_component_ids.add(component_id)
                contribution_id = UUID(contribution["uuid"])
                all_subject_ids.append(contribution_id)
        if len(all_subject_ids) != len(set(all_subject_ids)):
            raise SystemSecurityPlanValidationError(
                "SSP subject UUIDs must be unique across the document."
            )
        party_ids = {
            UUID(party["uuid"])
            for party in body["metadata"].get("parties", [])
            if "uuid" in party
        }
        document_uuid_fragments: set[str] = set()

        def collect_uuids(value: Any) -> None:
            if isinstance(value, Mapping):
                item_uuid = value.get("uuid")
                if isinstance(item_uuid, str):
                    document_uuid_fragments.add(item_uuid)
                for item in value.values():
                    collect_uuids(item)
            elif isinstance(value, list):
                for item in value:
                    collect_uuids(item)

        collect_uuids(body)

        def validate_references(value: Any) -> None:
            if isinstance(value, Mapping):
                party_uuid = value.get("party-uuid")
                if party_uuid is not None and UUID(party_uuid) not in party_ids:
                    raise SystemSecurityPlanValidationError(
                        f"SSP party reference {party_uuid!r} does not identify a metadata party."
                    )
                party_uuids = value.get("party-uuids", [])
                if any(UUID(item) not in party_ids for item in party_uuids):
                    raise SystemSecurityPlanValidationError(
                        "SSP responsible-party references must identify metadata parties."
                    )
                if value.get("rel") == "validation":
                    href = value.get("href", "")
                    if not href.startswith("#") or href[1:] not in document_uuid_fragments:
                        raise SystemSecurityPlanValidationError(
                            "SSP validation links must reference an internal UUID fragment."
                        )
                for item in value.values():
                    validate_references(item)
            elif isinstance(value, list):
                for item in value:
                    validate_references(item)

        validate_references(body)
    except SystemSecurityPlanValidationError:
        raise
    except OSError as error:
        raise SystemSecurityPlanValidationError(
            "The schema for the declared SSP version is unavailable."
        ) from error
    except JsonSchemaValidationError as error:
        path = ".".join(str(item) for item in error.absolute_path) or "<root>"
        raise SystemSecurityPlanValidationError(
            f"OSCAL SSP schema validation failed at {path}: {error.message}"
        ) from error
    except (KeyError, TypeError, ValueError, PydanticValidationError) as error:
        raise SystemSecurityPlanValidationError(
            "Document does not conform to its declared OSCAL System Security Plan model."
        ) from error
