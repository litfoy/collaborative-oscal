from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from jsonschema import Draft7Validator
from jsonschema import ValidationError as JsonSchemaValidationError

from collaborative_oscal_oscal.catalog_import import _OSCAL_DRAFT7_VALIDATOR
from collaborative_oscal_oscal.versions import (
    OscalDocumentModel,
    is_supported_oscal_version,
    load_oscal_schema,
    uses_json_schema,
)

DEFAULT_COMPONENT_OSCAL_VERSION = "1.2.3"


class ComponentDefinitionValidationError(ValueError):
    pass


def build_component_definition_document(
    *,
    document_uuid: UUID,
    title: str,
    components: Sequence[Mapping[str, Any]],
    last_modified: datetime | None = None,
    version: str = "1.0.0",
) -> dict[str, Any]:
    modified = last_modified or datetime.now(UTC)
    document = {
        "component-definition": {
            "uuid": str(document_uuid),
            "metadata": {
                "title": title,
                "last-modified": modified.isoformat().replace("+00:00", "Z"),
                "version": version,
                "oscal-version": DEFAULT_COMPONENT_OSCAL_VERSION,
            },
            "components": [dict(component) for component in components],
        }
    }
    validate_component_definition_document(document)
    return document


def validate_component_definition_document(document: Mapping[str, Any]) -> None:
    try:
        version = document["component-definition"]["metadata"]["oscal-version"]
        if not is_supported_oscal_version(OscalDocumentModel.COMPONENT_DEFINITION, version):
            raise ComponentDefinitionValidationError(
                "Unsupported OSCAL Component Definition version."
            )
        if not uses_json_schema(OscalDocumentModel.COMPONENT_DEFINITION, version):
            raise ComponentDefinitionValidationError(
                "No validator is configured for the declared OSCAL Component Definition version."
            )
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
    except (KeyError, TypeError, ValueError, JsonSchemaValidationError) as error:
        raise ComponentDefinitionValidationError(
            "Document does not conform to its declared OSCAL Component Definition model."
        ) from error
