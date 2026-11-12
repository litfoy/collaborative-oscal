from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from jsonschema import Draft7Validator
from jsonschema import ValidationError as JsonSchemaValidationError
from pydantic import ValidationError as PydanticValidationError
from trestle.oscal.profile import Model as TrestleProfileModel

from collaborative_oscal_oscal.catalog_import import (
    _OSCAL_DRAFT7_VALIDATOR,
)
from collaborative_oscal_oscal.versions import (
    DEFAULT_OSCAL_VERSION,
    OscalDocumentModel,
    is_supported_oscal_version,
    load_oscal_schema,
    uses_json_schema,
    uses_trestle_model,
)


class ProfileDocumentValidationError(ValueError):
    pass


def selected_control_ids(document: dict) -> list[str]:
    """Read the explicit selections from a Profile created by this application."""
    return list(document["profile"]["imports"][0]["include-controls"][0]["with-ids"])


def build_profile_document(
    *,
    profile_uuid: UUID,
    title: str,
    oscal_version: str = DEFAULT_OSCAL_VERSION,
    catalog_href: str = "",
    control_ids: Sequence[str] = (),
    imports: Sequence[tuple[str, Sequence[str]]] | None = None,
    version: str = "1.0.0",
    last_modified: datetime | None = None,
    description: str = "",
) -> dict:
    if not is_supported_oscal_version(OscalDocumentModel.PROFILE, oscal_version):
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
        if not is_supported_oscal_version(OscalDocumentModel.PROFILE, oscal_version):
            raise ProfileDocumentValidationError("Unsupported OSCAL version.")
        if uses_json_schema(OscalDocumentModel.PROFILE, oscal_version):
            _OSCAL_DRAFT7_VALIDATOR(
                load_oscal_schema(OscalDocumentModel.PROFILE, oscal_version),
                format_checker=Draft7Validator.FORMAT_CHECKER,
            ).validate(document)
        elif uses_trestle_model(OscalDocumentModel.PROFILE, oscal_version):
            TrestleProfileModel.model_validate(document)
        else:
            raise ProfileDocumentValidationError(
                "No validator is configured for the declared OSCAL version."
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
        JsonSchemaValidationError,
        PydanticValidationError,
    ) as error:
        raise ProfileDocumentValidationError(
            "OSCAL Profile does not conform to its declared OSCAL Profile model."
        ) from error
