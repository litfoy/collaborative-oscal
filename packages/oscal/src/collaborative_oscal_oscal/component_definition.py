# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from jsonschema import Draft7Validator
from jsonschema import ValidationError as JsonSchemaValidationError
from pydantic import ValidationError as PydanticValidationError
from trestle.oscal.component import Model as TrestleComponentModel

from collaborative_oscal_oscal.authoring import (
    OscalAuthoringError,
    format_oscal_timestamp,
    serialize_authored_document,
)
from collaborative_oscal_oscal.catalog_import import _OSCAL_DRAFT7_VALIDATOR
from collaborative_oscal_oscal.versions import (
    BUNDLED_JSON_SCHEMA_OSCAL_VERSIONS,
    OscalDocumentModel,
    authoring_version_for,
    authoring_version_for_component_types,
    is_supported_oscal_version,
    load_oscal_schema,
    uses_trestle_model,
)

DEFAULT_COMPONENT_OSCAL_VERSION = authoring_version_for(
    OscalDocumentModel.COMPONENT_DEFINITION
)


class ComponentDefinitionValidationError(ValueError):
    pass


def build_component_definition_document(
    *,
    document_uuid: UUID,
    title: str,
    components: Sequence[Mapping[str, Any]],
    last_modified: datetime | None = None,
    version: str = "1.0.0",
    oscal_version: str | None = None,
) -> dict[str, Any]:
    modified = last_modified or datetime.now(UTC)
    target_version = oscal_version or authoring_version_for(
        OscalDocumentModel.COMPONENT_DEFINITION
    )
    document = {
        "component-definition": {
            "uuid": str(document_uuid),
            "metadata": {
                "title": title,
                "last-modified": format_oscal_timestamp(modified),
                "version": version,
                "oscal-version": target_version,
            },
            "components": [dict(component) for component in components],
        }
    }
    if uses_trestle_model(OscalDocumentModel.COMPONENT_DEFINITION, target_version):
        try:
            return serialize_authored_document(
                TrestleComponentModel,
                document,
                OscalDocumentModel.COMPONENT_DEFINITION,
                target_version,
            )
        except OscalAuthoringError as error:
            raise ComponentDefinitionValidationError(str(error)) from error
    validate_component_definition_document(document)
    return document


def component_definition_authoring_version(component_types: Sequence[str]) -> str:
    return authoring_version_for_component_types(
        OscalDocumentModel.COMPONENT_DEFINITION, component_types
    )


def validate_component_definition_document(document: Mapping[str, Any]) -> None:
    try:
        version = document["component-definition"]["metadata"]["oscal-version"]
        if not is_supported_oscal_version(OscalDocumentModel.COMPONENT_DEFINITION, version):
            raise ComponentDefinitionValidationError(
                "Unsupported OSCAL Component Definition version."
            )
        if uses_trestle_model(OscalDocumentModel.COMPONENT_DEFINITION, version):
            TrestleComponentModel.model_validate(document)
        if version not in BUNDLED_JSON_SCHEMA_OSCAL_VERSIONS and not uses_trestle_model(
            OscalDocumentModel.COMPONENT_DEFINITION, version
        ):
            raise ComponentDefinitionValidationError(
                "No validator is configured for the declared OSCAL Component Definition version."
            )
        if version in BUNDLED_JSON_SCHEMA_OSCAL_VERSIONS:
            _OSCAL_DRAFT7_VALIDATOR(
                load_oscal_schema(OscalDocumentModel.COMPONENT_DEFINITION, version),
                format_checker=Draft7Validator.FORMAT_CHECKER,
            ).validate(document)
    except ComponentDefinitionValidationError:
        raise
    except OSError as error:
        raise ComponentDefinitionValidationError(
            "The schema for the declared OSCAL Component Definition version is unavailable."
        ) from error
    except (
        KeyError,
        TypeError,
        ValueError,
        JsonSchemaValidationError,
        PydanticValidationError,
    ) as error:
        raise ComponentDefinitionValidationError(
            "Document does not conform to its declared OSCAL Component Definition model."
        ) from error
