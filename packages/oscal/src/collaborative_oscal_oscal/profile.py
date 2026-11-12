from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from pydantic import ValidationError
from trestle.oscal.profile import Model

SUPPORTED_OSCAL_VERSIONS = frozenset({"1.1.3", "1.2.1"})


class ProfileDocumentValidationError(ValueError):
    pass


def selected_control_ids(document: dict) -> list[str]:
    """Read the explicit selections from a Profile created by this application."""
    return list(document["profile"]["imports"][0]["include-controls"][0]["with-ids"])


def build_profile_document(
    *,
    profile_uuid: UUID,
    title: str,
    oscal_version: str,
    catalog_href: str,
    control_ids: Sequence[str],
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
                    "href": catalog_href,
                    "include-controls": [{"with-ids": list(control_ids)}],
                }
            ],
        }
    }
    if description:
        document["profile"]["metadata"]["remarks"] = description

    try:
        Model.model_validate_json(json.dumps(document, allow_nan=False), strict=True)
    except (TypeError, ValueError, ValidationError) as error:
        raise ProfileDocumentValidationError(
            "Generated OSCAL Profile does not conform to the OSCAL Profile model."
        ) from error
    return document
