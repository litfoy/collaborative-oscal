from __future__ import annotations

import json
from collections.abc import Mapping
from enum import StrEnum
from functools import cache
from importlib.resources import files
from importlib.resources.abc import Traversable
from types import MappingProxyType
from typing import Any


class OscalDocumentModel(StrEnum):
    CATALOG = "catalog"
    PROFILE = "profile"


DEFAULT_OSCAL_VERSION = "1.2.3"
LEGACY_OSCAL_VERSIONS = (
    "1.0.0",
    "1.0.1",
    "1.0.2",
    "1.0.3",
    "1.0.4",
    "1.0.5",
    "1.0.6",
    "1.1.0",
    "1.1.1",
    "1.1.2",
)
TRESTLE_OSCAL_VERSIONS = ("1.1.3", "1.2.0", "1.2.1")
JSON_SCHEMA_OSCAL_VERSIONS = (*LEGACY_OSCAL_VERSIONS, "1.2.2", "1.2.3")
OSCAL_VERSION_ORDER = (*LEGACY_OSCAL_VERSIONS, *TRESTLE_OSCAL_VERSIONS, "1.2.2", "1.2.3")
SUPPORTED_OSCAL_VERSIONS_BY_MODEL: Mapping[OscalDocumentModel, tuple[str, ...]] = MappingProxyType(
    {
        OscalDocumentModel.CATALOG: OSCAL_VERSION_ORDER,
        OscalDocumentModel.PROFILE: OSCAL_VERSION_ORDER,
    }
)
SUPPORTED_OSCAL_DOCUMENT_MODELS_BY_VERSION: Mapping[str, frozenset[OscalDocumentModel]] = (
    MappingProxyType(
        {
            version: frozenset(
                model
                for model, supported_versions in SUPPORTED_OSCAL_VERSIONS_BY_MODEL.items()
                if version in supported_versions
            )
            for version in OSCAL_VERSION_ORDER
        }
    )
)
SUPPORTED_OSCAL_VERSIONS = frozenset(SUPPORTED_OSCAL_DOCUMENT_MODELS_BY_VERSION)


def is_supported_oscal_version(model: OscalDocumentModel, version: str) -> bool:
    return model in SUPPORTED_OSCAL_DOCUMENT_MODELS_BY_VERSION.get(version, frozenset())


def schema_resource(model: OscalDocumentModel, version: str) -> Traversable:
    if not is_supported_oscal_version(model, version) or version not in JSON_SCHEMA_OSCAL_VERSIONS:
        raise ValueError(
            f"No bundled JSON Schema is registered for OSCAL {model.value} version {version!r}."
        )
    return files("collaborative_oscal_oscal").joinpath(
        "schemas", f"oscal_{model.value}_schema_v{version}.json"
    )


@cache
def load_oscal_schema(model: OscalDocumentModel, version: str) -> dict[str, Any]:
    return json.loads(schema_resource(model, version).read_text(encoding="utf-8"))


def uses_json_schema(model: OscalDocumentModel, version: str) -> bool:
    return is_supported_oscal_version(model, version) and version in JSON_SCHEMA_OSCAL_VERSIONS


def uses_trestle_model(model: OscalDocumentModel, version: str) -> bool:
    return is_supported_oscal_version(model, version) and version in TRESTLE_OSCAL_VERSIONS
