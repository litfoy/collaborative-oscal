from __future__ import annotations

import json
import math
import types
from dataclasses import dataclass
from enum import StrEnum
from importlib.metadata import version
from typing import Any, Union, get_args, get_origin

import yaml
from pydantic import ValidationError
from yaml.events import (
    AliasEvent,
    DocumentStartEvent,
    MappingEndEvent,
    MappingStartEvent,
    SequenceEndEvent,
    SequenceStartEvent,
)
from yaml.loader import SafeLoader
from yaml.nodes import MappingNode

from collaborative_oscal_oscal.catalog_index import project_catalog_indexes

SUPPORTED_OSCAL_VERSIONS = frozenset({"1.2.1"})
VALIDATOR_NAME = "compliance-trestle"
VALIDATOR_VERSION = version("compliance-trestle")
DEFAULT_MAX_INPUT_BYTES = 5 * 1024 * 1024
DEFAULT_MAX_NESTING_DEPTH = 64
MODEL_VALIDATION_WARNING = (
    "Trestle Pydantic model validation is not a claim of exhaustive NIST Metaschema "
    "semantic validation."
)

_OSCAL_MODELS = frozenset(
    {
        "assessment-plan",
        "assessment-results",
        "catalog",
        "component-definition",
        "control-mapping",
        "plan-of-action-and-milestones",
        "profile",
        "system-security-plan",
    }
)


class CatalogInputFormat(StrEnum):
    AUTO = "auto"
    JSON = "json"
    YAML = "yaml"


@dataclass(frozen=True, slots=True)
class CatalogValidationError:
    code: str
    message: str
    path: str | None = None
    diagnostic: str | None = None


@dataclass(frozen=True, slots=True)
class CatalogValidationResult:
    valid: bool
    document_type: str | None
    declared_oscal_version: str | None
    validator_name: str
    validator_version: str
    validation_schema_version: str | None
    errors: tuple[CatalogValidationError, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CatalogValidationOutcome:
    result: CatalogValidationResult
    document: dict[str, Any] | None = None
    input_format: CatalogInputFormat | None = None


class _DuplicateJsonKey(ValueError):
    pass


class _DuplicateYamlKey(ValueError):
    pass


class _UnsupportedYamlKey(ValueError):
    pass


class _SafeCatalogLoader(SafeLoader):
    yaml_implicit_resolvers = {
        key: [(tag, regexp) for tag, regexp in resolvers if tag != "tag:yaml.org,2002:timestamp"]
        for key, resolvers in SafeLoader.yaml_implicit_resolvers.items()
    }

    def construct_mapping(self, node: MappingNode, deep: bool = False) -> dict[str, Any]:
        if not isinstance(node, MappingNode):
            raise yaml.constructor.ConstructorError(
                None, None, "Expected a mapping node.", node.start_mark
            )
        mapping: dict[str, Any] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise _UnsupportedYamlKey
            if key in mapping:
                raise _DuplicateYamlKey
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"Non-finite JSON number: {value}")


def _pointer(parts: tuple[Any, ...]) -> str:
    escaped = (str(part).replace("~", "~0").replace("/", "~1") for part in parts)
    return "/" + "/".join(escaped)


def _unknown_model_fields(
    value: Any, model_type: type[Any], path: tuple[str, ...] = ()
) -> list[tuple[tuple[str, ...], str]]:
    from pydantic import BaseModel

    if not isinstance(value, dict) or not issubclass(model_type, BaseModel):
        return []
    fields = {
        field.alias or name: field.annotation for name, field in model_type.model_fields.items()
    }
    errors: list[tuple[tuple[str, ...], str]] = []
    for key, child in value.items():
        annotation = fields.get(key)
        if annotation is None:
            if not key.startswith("x-"):
                errors.append(((*path, key), "Field is not defined by the OSCAL model."))
            continue
        errors.extend(_unknown_fields_for_annotation(child, annotation, (*path, key)))
    return errors


def _unknown_fields_for_annotation(
    value: Any, annotation: Any, path: tuple[str, ...]
) -> list[tuple[tuple[str, ...], str]]:
    from pydantic import BaseModel

    origin = get_origin(annotation)
    if origin is types.UnionType or origin is Union:
        candidates = [
            item
            for item in get_args(annotation)
            if isinstance(item, type) and issubclass(item, BaseModel)
        ]
        if candidates:
            return min(
                (_unknown_model_fields(value, candidate, path) for candidate in candidates),
                key=len,
            )
    if origin is list:
        item_type = get_args(annotation)[0]
        return [
            error
            for index, item in enumerate(value if isinstance(value, list) else [])
            for error in _unknown_fields_for_annotation(item, item_type, (*path, str(index)))
        ]
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return _unknown_model_fields(value, annotation, path)
    return []


def _error(
    code: str,
    message: str,
    *,
    path: str | None = None,
    diagnostic: str | None = None,
    document_type: str | None = None,
    declared_version: str | None = None,
) -> CatalogValidationOutcome:
    return CatalogValidationOutcome(
        CatalogValidationResult(
            valid=False,
            document_type=document_type,
            declared_oscal_version=declared_version,
            validator_name=VALIDATOR_NAME,
            validator_version=VALIDATOR_VERSION,
            validation_schema_version=(
                f"OSCAL {declared_version}"
                if declared_version in SUPPORTED_OSCAL_VERSIONS
                else None
            ),
            errors=(CatalogValidationError(code, message, path, diagnostic),),
        )
    )


def _detect_format(content: bytes) -> CatalogInputFormat:
    normalized = content.lstrip()
    if normalized.startswith(b"\xef\xbb\xbf"):
        normalized = normalized[3:].lstrip()
    first = normalized[:1]
    return CatalogInputFormat.JSON if first == b"{" else CatalogInputFormat.YAML


def _check_json_depth(text: str, max_depth: int) -> bool:
    depth = 0
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            if depth > max_depth:
                return False
        elif char in "]}":
            depth -= 1
    return True


def _check_yaml_events(text: str, max_depth: int) -> str | None:
    depth = 0
    documents = 0
    try:
        for event in yaml.parse(text, Loader=_SafeCatalogLoader):
            if isinstance(event, AliasEvent):
                return "YAML aliases are not supported."
            if isinstance(event, DocumentStartEvent):
                documents += 1
                if documents > 1:
                    return "Only one YAML document is supported."
            if isinstance(event, (MappingStartEvent, SequenceStartEvent)):
                depth += 1
                if depth > max_depth:
                    return "The document exceeds the maximum nesting depth."
            elif isinstance(event, (MappingEndEvent, SequenceEndEvent)):
                depth -= 1
    except yaml.YAMLError:
        return "The YAML document is syntactically invalid."
    return None


def _validate_tree(value: Any) -> bool:
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            return False
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(
            isinstance(key, str) and _validate_tree(key) and _validate_tree(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return all(_validate_tree(item) for item in value)
    return value is None or isinstance(value, (str, bool, int))


def _parse(
    content: bytes,
    input_format: CatalogInputFormat | str,
    *,
    max_input_bytes: int,
    max_nesting_depth: int,
) -> tuple[dict[str, Any] | None, CatalogInputFormat | None, CatalogValidationOutcome | None]:
    if not isinstance(content, bytes):
        return None, None, _error("UNSUPPORTED_INPUT", "Catalog input must be raw bytes.")
    if not content:
        return None, None, _error("EMPTY_INPUT", "Catalog input is empty.")
    if len(content) > max_input_bytes:
        return (
            None,
            None,
            _error("INPUT_TOO_LARGE", "Catalog input exceeds the configured size limit."),
        )
    try:
        selected_format = CatalogInputFormat(input_format)
    except (TypeError, ValueError):
        return None, None, _error("UNSUPPORTED_FORMAT", "Input format must be JSON, YAML, or auto.")
    if selected_format is CatalogInputFormat.AUTO:
        selected_format = _detect_format(content)
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return (
            None,
            selected_format,
            _error("UNSUPPORTED_ENCODING", "Input must use UTF-8 encoding."),
        )

    try:
        if selected_format is CatalogInputFormat.JSON:
            if not _check_json_depth(text, max_nesting_depth):
                return (
                    None,
                    selected_format,
                    _error("MAX_NESTING_DEPTH", "The document exceeds the maximum nesting depth."),
                )
            value = json.loads(
                text,
                object_pairs_hook=_json_object,
                parse_constant=_reject_json_constant,
            )
        else:
            event_error = _check_yaml_events(text, max_nesting_depth)
            if event_error is not None:
                code = (
                    "MAX_NESTING_DEPTH"
                    if "maximum nesting depth" in event_error
                    else "UNSUPPORTED_YAML_FEATURE"
                    if "aliases" in event_error or "one YAML document" in event_error
                    else "YAML_SYNTAX_INVALID"
                )
                return None, selected_format, _error(code, event_error)
            value = yaml.load(text, Loader=_SafeCatalogLoader)
    except _DuplicateJsonKey:
        return (
            None,
            selected_format,
            _error("DUPLICATE_OBJECT_KEY", "JSON contains a duplicate object key."),
        )
    except _DuplicateYamlKey:
        return (
            None,
            selected_format,
            _error("DUPLICATE_OBJECT_KEY", "YAML contains a duplicate mapping key."),
        )
    except _UnsupportedYamlKey:
        return (
            None,
            selected_format,
            _error("INVALID_DOCUMENT_STRUCTURE", "YAML mapping keys must be strings."),
        )
    except json.JSONDecodeError as exception:
        return (
            None,
            selected_format,
            _error(
                "JSON_SYNTAX_INVALID",
                f"JSON syntax is invalid at line {exception.lineno}, column {exception.colno}.",
                diagnostic=exception.msg,
            ),
        )
    except (UnicodeDecodeError, yaml.YAMLError, ValueError, RecursionError):
        code = (
            "JSON_SYNTAX_INVALID"
            if selected_format is CatalogInputFormat.JSON
            else "YAML_SYNTAX_INVALID"
        )
        return (
            None,
            selected_format,
            _error(code, f"{selected_format.value.upper()} syntax is invalid."),
        )

    if not _validate_tree(value):
        return (
            None,
            selected_format,
            _error(
                "INVALID_DOCUMENT_STRUCTURE",
                "The document contains unsupported or non-finite values.",
            ),
        )
    if not isinstance(value, dict):
        return (
            None,
            selected_format,
            _error("INVALID_DOCUMENT_STRUCTURE", "The OSCAL document root must be an object."),
        )
    return value, selected_format, None


def validate_catalog_bytes(
    content: bytes,
    input_format: CatalogInputFormat | str = CatalogInputFormat.AUTO,
    *,
    max_input_bytes: int = DEFAULT_MAX_INPUT_BYTES,
    max_nesting_depth: int = DEFAULT_MAX_NESTING_DEPTH,
) -> CatalogValidationOutcome:
    document, selected_format, parse_error = _parse(
        content,
        input_format,
        max_input_bytes=max_input_bytes,
        max_nesting_depth=max_nesting_depth,
    )
    if parse_error is not None:
        return parse_error
    assert document is not None
    model_types = [key for key in document if key in _OSCAL_MODELS]
    document_type = model_types[0] if len(model_types) == 1 else None
    if document_type != "catalog" or len(model_types) != 1:
        found_type = document_type or (model_types[0] if model_types else None)
        return _error(
            "UNSUPPORTED_DOCUMENT_TYPE",
            "Input must contain exactly one OSCAL Catalog root object.",
            document_type=found_type,
        )

    catalog = document["catalog"]
    if not isinstance(catalog, dict):
        return _error(
            "INVALID_DOCUMENT_STRUCTURE",
            "The OSCAL catalog root must be an object.",
            document_type="catalog",
        )
    metadata = catalog.get("metadata")
    declared_version = metadata.get("oscal-version") if isinstance(metadata, dict) else None
    if not isinstance(declared_version, str) or not declared_version:
        return _error(
            "MISSING_OSCAL_VERSION",
            "Catalog metadata must declare a non-empty oscal-version.",
            path="/catalog/metadata/oscal-version",
            document_type="catalog",
        )
    if declared_version not in SUPPORTED_OSCAL_VERSIONS:
        return _error(
            "UNSUPPORTED_OSCAL_VERSION",
            f"OSCAL version {declared_version!r} is not supported; supported version: 1.2.1.",
            path="/catalog/metadata/oscal-version",
            document_type="catalog",
            declared_version=declared_version,
        )

    from trestle.oscal.catalog import Model

    extension_errors = _unknown_model_fields(document, Model)
    if extension_errors:
        errors = tuple(
            CatalogValidationError(
                code="OSCAL_MODEL_INVALID",
                message=message,
                path=_pointer(error_path),
                diagnostic="extra_forbidden",
            )
            for error_path, message in extension_errors
        )
        return CatalogValidationOutcome(
            CatalogValidationResult(
                valid=False,
                document_type="catalog",
                declared_oscal_version=declared_version,
                validator_name=VALIDATOR_NAME,
                validator_version=VALIDATOR_VERSION,
                validation_schema_version=f"OSCAL {declared_version}",
                errors=errors,
                warnings=(MODEL_VALIDATION_WARNING,),
            )
        )

    try:
        model_json = json.dumps(document, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, RecursionError):
        return _error(
            "INVALID_DOCUMENT_STRUCTURE",
            "Document values cannot be represented as OSCAL JSON.",
            document_type="catalog",
            declared_version=declared_version,
        )
    try:
        Model.model_validate_json(model_json, strict=True, extra="allow")
    except ValidationError as exception:
        errors = tuple(
            CatalogValidationError(
                code="OSCAL_MODEL_INVALID",
                message=issue["msg"],
                path=_pointer(tuple(issue["loc"])),
                diagnostic=issue["type"],
            )
            for issue in exception.errors(include_input=False, include_context=False)
        )
        return CatalogValidationOutcome(
            CatalogValidationResult(
                valid=False,
                document_type="catalog",
                declared_oscal_version=declared_version,
                validator_name=VALIDATOR_NAME,
                validator_version=VALIDATOR_VERSION,
                validation_schema_version=f"OSCAL {declared_version}",
                errors=errors,
                warnings=(MODEL_VALIDATION_WARNING,),
            )
        )

    try:
        _, controls = project_catalog_indexes(document)
    except ValueError as exception:
        message = str(exception)
        path_start = message.rfind(" at ")
        path = message[path_start + 4 :] if path_start >= 0 else None
        return _error(
            "CATALOG_INDEX_INVALID",
            message,
            path=path,
            document_type="catalog",
            declared_version=declared_version,
        )
    seen_control_ids: set[str] = set()
    for control in controls:
        if control.oscal_control_id in seen_control_ids:
            return _error(
                "DUPLICATE_CONTROL_ID",
                "Catalog control identifiers must be unique within the catalog.",
                path=control.structural_path,
                document_type="catalog",
                declared_version=declared_version,
            )
        seen_control_ids.add(control.oscal_control_id)

    return CatalogValidationOutcome(
        CatalogValidationResult(
            valid=True,
            document_type="catalog",
            declared_oscal_version=declared_version,
            validator_name=VALIDATOR_NAME,
            validator_version=VALIDATOR_VERSION,
            validation_schema_version=f"OSCAL {declared_version}",
            warnings=(MODEL_VALIDATION_WARNING,),
        ),
        document=document,
        input_format=selected_format,
    )
