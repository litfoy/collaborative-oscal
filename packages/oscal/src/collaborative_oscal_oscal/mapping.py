from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from jsonschema import Draft7Validator
from jsonschema import ValidationError as JsonSchemaValidationError
from pydantic import ValidationError as PydanticValidationError
from trestle.oscal.mapping import Model as TrestleMappingModel

from collaborative_oscal_oscal.catalog_import import _OSCAL_DRAFT7_VALIDATOR
from collaborative_oscal_oscal.versions import (
    OscalDocumentModel,
    is_supported_oscal_version,
    load_oscal_schema,
    uses_json_schema,
    uses_trestle_model,
)

RELATIONSHIP_TYPES = frozenset(
    {
        "equal-to",
        "equivalent-to",
        "subset-of",
        "superset-of",
        "intersects-with",
        "no-relationship",
    }
)
MATCHING_RATIONALES = frozenset({"syntactic", "semantic", "functional"})
MAPPING_METHODS = frozenset({"human", "automation", "hybrid"})
MAPPING_STATUSES = frozenset(
    {"complete", "not-complete", "draft", "deprecated", "superseded"}
)


class MappingDocumentValidationError(ValueError):
    pass


def validate_mapping_document(document: Mapping[str, Any]) -> None:
    try:
        collection = document["mapping-collection"]
        oscal_version = collection["metadata"]["oscal-version"]
        if not is_supported_oscal_version(OscalDocumentModel.MAPPING, oscal_version):
            raise MappingDocumentValidationError("Unsupported OSCAL Mapping version.")
        if uses_json_schema(OscalDocumentModel.MAPPING, oscal_version):
            _OSCAL_DRAFT7_VALIDATOR(
                load_oscal_schema(OscalDocumentModel.MAPPING, oscal_version),
                format_checker=Draft7Validator.FORMAT_CHECKER,
            ).validate(document)
        elif uses_trestle_model(OscalDocumentModel.MAPPING, oscal_version):
            TrestleMappingModel.model_validate(document)
        else:
            raise MappingDocumentValidationError(
                "No validator is configured for the declared OSCAL Mapping version."
            )
    except MappingDocumentValidationError:
        raise
    except OSError as error:
        raise MappingDocumentValidationError(
            "The schema for the declared OSCAL Mapping version is unavailable."
        ) from error
    except (
        KeyError,
        TypeError,
        ValueError,
        JsonSchemaValidationError,
        PydanticValidationError,
    ) as error:
        raise MappingDocumentValidationError(
            "OSCAL Mapping does not conform to its declared OSCAL Mapping model."
        ) from error


def relationship_from_opposite_direction(relationship: str) -> str:
    if relationship == "subset-of":
        return "superset-of"
    if relationship == "superset-of":
        return "subset-of"
    return relationship
