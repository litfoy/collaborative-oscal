# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from jsonschema import Draft7Validator
from jsonschema import ValidationError as JsonSchemaValidationError
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from collaborative_oscal_oscal.catalog_import import _OSCAL_DRAFT7_VALIDATOR
from collaborative_oscal_oscal.versions import (
    OscalDocumentModel,
    document_root_key,
    is_supported_oscal_version,
    load_oscal_schema,
    uses_trestle_model,
)

_DATETIME_FIELDS = frozenset(
    {"last-modified", "published", "start", "end", "collected", "expires"}
)


class OscalAuthoringError(ValueError):
    pass


def format_oscal_timestamp(value: datetime) -> str:
    modified = value.astimezone(UTC).replace(microsecond=0)
    return modified.isoformat(timespec="seconds").replace("+00:00", "Z")


def serialize_authored_document[TrestleModel: BaseModel](
    model_type: type[TrestleModel],
    document: Mapping[str, Any],
    document_model: OscalDocumentModel,
    version: str,
) -> dict[str, Any]:
    if not is_supported_oscal_version(document_model, version):
        raise OscalAuthoringError(
            f"Unsupported OSCAL {document_model.value} version {version!r}."
        )
    if not uses_trestle_model(document_model, version):
        raise OscalAuthoringError(
            f"No compatible Compliance Trestle model is configured for OSCAL "
            f"{document_model.value} {version}."
        )
    try:
        root_key = document_root_key(document_model)
        body = document[root_key]
        if body["metadata"]["oscal-version"] != version:
            raise OscalAuthoringError(
                "The declared OSCAL version does not match the selected authoring version."
            )
        serialized = model_type.model_validate(document).model_dump(
            mode="json", by_alias=True, exclude_unset=True
        )
        if not isinstance(serialized, dict) or not _same_document(document, serialized):
            raise OscalAuthoringError(
                "Compliance Trestle serialization changed explicitly authored OSCAL content."
            )
        schema = load_oscal_schema(document_model, version)
        _OSCAL_DRAFT7_VALIDATOR(
            schema, format_checker=Draft7Validator.FORMAT_CHECKER
        ).validate(serialized)
    except OscalAuthoringError:
        raise
    except (KeyError, TypeError, OSError, ValueError, PydanticValidationError) as error:
        raise OscalAuthoringError(
            f"Unable to serialize OSCAL {document_model.value} {version} "
            "with the Compliance Trestle model and official schema."
        ) from error
    except JsonSchemaValidationError as error:
        raise OscalAuthoringError(
            f"Serialized OSCAL {document_model.value} {version} document failed "
            "official NIST JSON Schema validation."
        ) from error
    return serialized


def _same_document(original: Any, serialized: Any, key: str | None = None) -> bool:
    if isinstance(original, Mapping):
        return (
            isinstance(serialized, Mapping)
            and original.keys() == serialized.keys()
            and all(_same_document(original[item], serialized[item], item) for item in original)
        )
    if isinstance(original, list):
        return (
            isinstance(serialized, list)
            and len(original) == len(serialized)
            and all(_same_document(left, right) for left, right in zip(original, serialized))
        )
    if key in _DATETIME_FIELDS and isinstance(original, str) and isinstance(serialized, str):
        try:
            left = datetime.fromisoformat(original)
            right = datetime.fromisoformat(serialized)
        except ValueError:
            return False
        return left == right
    return type(original) is type(serialized) and original == serialized
