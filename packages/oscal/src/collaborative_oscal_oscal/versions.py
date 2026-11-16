from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from enum import StrEnum
from functools import cache
from importlib.resources import files
from importlib.resources.abc import Traversable
from types import MappingProxyType
from typing import Any


class OscalDocumentModel(StrEnum):
    CATALOG = "catalog"
    COMPONENT_DEFINITION = "component-definition"
    MAPPING = "mapping"
    PROFILE = "profile"
    SYSTEM_SECURITY_PLAN = "system-security-plan"


DEFAULT_AUTHORING_OSCAL_VERSION = "1.2.1"
OSCAL_123_ONLY_COMPONENT_TYPES_BY_MODEL = MappingProxyType(
    {
        OscalDocumentModel.COMPONENT_DEFINITION: frozenset(
            {"network", "region", "zone", "resource-container"}
        ),
        OscalDocumentModel.SYSTEM_SECURITY_PLAN: frozenset(
            {"region", "zone", "resource-container"}
        ),
    }
)
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
BUNDLED_JSON_SCHEMA_OSCAL_VERSIONS = (
    *LEGACY_OSCAL_VERSIONS,
    "1.2.1",
    "1.2.2",
    "1.2.3",
)
OSCAL_VERSION_ORDER = (
    *LEGACY_OSCAL_VERSIONS,
    *TRESTLE_OSCAL_VERSIONS,
    "1.2.2",
    "1.2.3",
)
SUPPORTED_OSCAL_VERSIONS_BY_MODEL: Mapping[OscalDocumentModel, tuple[str, ...]] = (
    MappingProxyType(
        {
            OscalDocumentModel.CATALOG: OSCAL_VERSION_ORDER,
            OscalDocumentModel.COMPONENT_DEFINITION: ("1.2.1", "1.2.3"),
            OscalDocumentModel.MAPPING: ("1.2.0", "1.2.1", "1.2.2", "1.2.3"),
            OscalDocumentModel.PROFILE: OSCAL_VERSION_ORDER,
            OscalDocumentModel.SYSTEM_SECURITY_PLAN: ("1.2.1", "1.2.3"),
        }
    )
)
SUPPORTED_OSCAL_DOCUMENT_MODELS_BY_VERSION: Mapping[
    str, frozenset[OscalDocumentModel]
] = MappingProxyType(
    {
        version: frozenset(
            model
            for model, supported_versions in SUPPORTED_OSCAL_VERSIONS_BY_MODEL.items()
            if version in supported_versions
        )
        for version in OSCAL_VERSION_ORDER
    }
)
SUPPORTED_OSCAL_VERSIONS = frozenset(SUPPORTED_OSCAL_DOCUMENT_MODELS_BY_VERSION)
AUTHORING_OSCAL_VERSION_BY_MODEL: Mapping[OscalDocumentModel, str] = (
    MappingProxyType(
        {
            OscalDocumentModel.PROFILE: DEFAULT_AUTHORING_OSCAL_VERSION,
            OscalDocumentModel.MAPPING: DEFAULT_AUTHORING_OSCAL_VERSION,
            OscalDocumentModel.COMPONENT_DEFINITION: DEFAULT_AUTHORING_OSCAL_VERSION,
            OscalDocumentModel.SYSTEM_SECURITY_PLAN: DEFAULT_AUTHORING_OSCAL_VERSION,
        }
    )
)

# Kept as compatibility aliases for existing package callers.
DEFAULT_OSCAL_VERSION = AUTHORING_OSCAL_VERSION_BY_MODEL[OscalDocumentModel.PROFILE]
DEFAULT_MAPPING_OSCAL_VERSION = AUTHORING_OSCAL_VERSION_BY_MODEL[OscalDocumentModel.MAPPING]


def is_supported_oscal_version(model: OscalDocumentModel, version: str) -> bool:
    return model in SUPPORTED_OSCAL_DOCUMENT_MODELS_BY_VERSION.get(version, frozenset())


def authoring_version_for(model: OscalDocumentModel) -> str:
    try:
        version = AUTHORING_OSCAL_VERSION_BY_MODEL[model]
    except KeyError as error:
        raise ValueError(f"No authoring version is configured for OSCAL {model.value}.") from error
    if not is_supported_oscal_version(model, version) or not uses_trestle_model(
        model, version
    ):
        raise ValueError(
            f"OSCAL {model.value} authoring version {version!r} has no compatible "
            "Compliance Trestle model."
        )
    return version


def authoring_version_for_component_types(
    model: OscalDocumentModel, component_types: Sequence[str]
) -> str:
    if model not in {
        OscalDocumentModel.COMPONENT_DEFINITION,
        OscalDocumentModel.SYSTEM_SECURITY_PLAN,
    }:
        raise ValueError(f"Component types do not select an OSCAL {model.value} version.")
    if OSCAL_123_ONLY_COMPONENT_TYPES_BY_MODEL[model].intersection(component_types):
        return "1.2.3"
    return authoring_version_for(model)


def schema_resource(model: OscalDocumentModel, version: str) -> Traversable:
    if (
        not is_supported_oscal_version(model, version)
        or version not in BUNDLED_JSON_SCHEMA_OSCAL_VERSIONS
    ):
        raise ValueError(
            f"No bundled JSON Schema is registered for OSCAL {model.value} version {version!r}."
        )
    schema_name = (
        "oscal_component_definition_schema"
        if model is OscalDocumentModel.COMPONENT_DEFINITION
        else "oscal_ssp_schema"
        if model is OscalDocumentModel.SYSTEM_SECURITY_PLAN
        else f"oscal_{model.value.replace('-', '_')}_schema"
    )
    return files("collaborative_oscal_oscal").joinpath(
        "schemas", f"{schema_name}_v{version}.json"
    )


@cache
def load_oscal_schema(model: OscalDocumentModel, version: str) -> dict[str, Any]:
    return json.loads(schema_resource(model, version).read_text(encoding="utf-8"))


def uses_json_schema(model: OscalDocumentModel, version: str) -> bool:
    return (
        is_supported_oscal_version(model, version)
        and version in JSON_SCHEMA_OSCAL_VERSIONS
    )


def uses_trestle_model(model: OscalDocumentModel, version: str) -> bool:
    return (
        is_supported_oscal_version(model, version) and version in TRESTLE_OSCAL_VERSIONS
    )
