from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from functools import cache
from importlib.resources import files
from uuid import UUID

from jsonschema import ValidationError as JsonSchemaValidationError
from pydantic import ValidationError
from trestle.oscal.profile import Model

from collaborative_oscal_oscal.catalog_import import (
    _OSCAL_DRAFT7_VALIDATOR,
    SUPPORTED_OSCAL_VERSIONS,
    _unknown_model_fields,
)


class ProfileDocumentValidationError(ValueError):
    pass


@cache
def _profile_schema(oscal_version: str) -> dict:
    return json.loads(
        files("collaborative_oscal_oscal")
        .joinpath("schemas", f"oscal_profile_schema_v{oscal_version}.json")
        .read_text(encoding="utf-8")
    )


def selected_control_ids(document: dict) -> list[str]:
    """Read the explicit selections from a Profile created by this application."""
    return list(document["profile"]["imports"][0]["include-controls"][0]["with-ids"])


def build_profile_document(
    *,
    profile_uuid: UUID,
    title: str,
    oscal_version: str,
    catalog_href: str = "",
    control_ids: Sequence[str] = (),
    imports: Sequence[tuple[str, Sequence[str]]] | None = None,
    version: str = "1.0.0",
    last_modified: datetime | None = None,
    description: str = "",
) -> dict:
    if oscal_version not in SUPPORTED_OSCAL_VERSIONS:
        raise ProfileDocumentValidationError("Unsupported OSCAL version.")

    modified = last_modified or datetime.now(UTC)
    document = {
        "profile": {
            "uuid": str(profile_uuid),
            "metadata": {
                "title": title,
                "last-modified": modified.isoformat().replace("+00:00", "Z"),
                "version": version,
                "oscal-version": oscal_version,
            },
            "imports": [
                {
                    "href": href,
                    "include-controls": [{"with-ids": list(ids)}],
                }
                for href, ids in (
                    imports if imports is not None else [(catalog_href, control_ids)]
                )
            ],
        }
    }
    if description:
        document["profile"]["metadata"]["remarks"] = description

    validate_profile_document(document)
    return document


def validate_profile_document(document: dict) -> None:
    try:
        oscal_version = document["profile"]["metadata"]["oscal-version"]
        if oscal_version not in SUPPORTED_OSCAL_VERSIONS:
            raise ProfileDocumentValidationError("Unsupported OSCAL version.")
        _OSCAL_DRAFT7_VALIDATOR(_profile_schema(oscal_version)).validate(document)
        if oscal_version == "1.2.1":
            if _unknown_model_fields(document, Model):
                raise ProfileDocumentValidationError(
                    "OSCAL Profile contains fields not defined by its declared model."
                )
            Model.model_validate_json(
                json.dumps(document, allow_nan=False), strict=True
            )
    except ProfileDocumentValidationError:
        raise
    except OSError as error:
        raise ProfileDocumentValidationError(
            "The schema for the declared OSCAL Profile version is unavailable."
        ) from error
    except (
        KeyError,
        TypeError,
        ValueError,
        ValidationError,
        JsonSchemaValidationError,
    ) as error:
        raise ProfileDocumentValidationError(
            "OSCAL Profile does not conform to its declared OSCAL Profile model."
        ) from error
