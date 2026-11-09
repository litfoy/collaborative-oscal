"""Read-only projections of OSCAL catalog content for presentation.

Functions never mutate their input. Unknown or malformed optional elements are
skipped rather than rejected, because documents were validated at import time and
extension data is intentionally preserved in storage.
"""

from collections.abc import Mapping, Sequence
from typing import Any

MAX_PART_DEPTH = 32
_PATH_SEGMENT_KINDS = {"groups", "controls"}


def jsonb_path_for_structural_path(structural_path: str) -> list[str]:
    """Convert an indexed structural path to a JSONB path below the document root.

    Only the generated `/catalog(/groups|controls/<n>)*` shape is accepted so the
    result can never address anything other than a group or control.
    """
    segments = structural_path.split("/")
    if len(segments) < 2 or segments[0] != "" or segments[1] != "catalog":
        raise ValueError("Unsupported structural path.")
    rest = segments[2:]
    if len(rest) % 2 != 0:
        raise ValueError("Unsupported structural path.")
    for kind, position in zip(rest[::2], rest[1::2], strict=True):
        if kind not in _PATH_SEGMENT_KINDS or not position.isdigit():
            raise ValueError("Unsupported structural path.")
    return ["catalog", *rest]


def ancestor_structural_paths(structural_path: str) -> list[str]:
    """Return ancestor paths (outermost first) that identify groups and controls."""
    jsonb_path_for_structural_path(structural_path)
    segments = structural_path.split("/")[2:]
    ancestors = [
        "/catalog/" + "/".join(segments[:end]) for end in range(2, len(segments), 2)
    ]
    return ancestors


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def project_property(value: Mapping[str, Any]) -> dict[str, Any] | None:
    name, text = _text(value.get("name")), _text(value.get("value"))
    if name is None or text is None:
        return None
    return {
        "name": name,
        "value": text,
        "ns": _text(value.get("ns")),
        "class": _text(value.get("class")),
        "uuid": _text(value.get("uuid")),
        "remarks": _text(value.get("remarks")),
    }


def project_properties(values: Any) -> list[dict[str, Any]]:
    projected = (project_property(item) for item in _mappings(values))
    return [item for item in projected if item is not None]


def project_links(values: Any) -> list[dict[str, Any]]:
    links = []
    for item in _mappings(values):
        href = _text(item.get("href"))
        if href is None:
            continue
        links.append(
            {
                "href": href,
                "rel": _text(item.get("rel")),
                "text": _text(item.get("text")),
                "media_type": _text(item.get("media-type")),
            }
        )
    return links


def project_part(value: Mapping[str, Any], depth: int = 0) -> dict[str, Any]:
    nested = (
        [project_part(child, depth + 1) for child in _mappings(value.get("parts"))]
        if depth < MAX_PART_DEPTH
        else []
    )
    return {
        "id": _text(value.get("id")),
        "name": _text(value.get("name")) or "",
        "ns": _text(value.get("ns")),
        "class": _text(value.get("class")),
        "title": _text(value.get("title")),
        "prose": _text(value.get("prose")),
        "props": project_properties(value.get("props")),
        "links": project_links(value.get("links")),
        "parts": nested,
    }


def project_parameter(value: Mapping[str, Any]) -> dict[str, Any] | None:
    identifier = _text(value.get("id"))
    if identifier is None:
        return None
    select = value.get("select")
    projected_select = None
    if isinstance(select, Mapping):
        projected_select = {
            "how_many": _text(select.get("how-many")),
            "choices": _strings(select.get("choice")),
        }
    constraints = [
        {
            "description": _text(constraint.get("description")),
            "tests": [
                {"expression": _text(test.get("expression")) or "", "remarks": _text(test.get("remarks"))}
                for test in _mappings(constraint.get("tests"))
            ],
        }
        for constraint in _mappings(value.get("constraints"))
    ]
    guidelines = [
        text for text in (_text(item.get("prose")) for item in _mappings(value.get("guidelines"))) if text
    ]
    depends_on = value.get("depends-on")
    return {
        "id": identifier,
        "class": _text(value.get("class")),
        "label": _text(value.get("label")),
        "usage": _text(value.get("usage")),
        "values": _strings(value.get("values")),
        "select": projected_select,
        "constraints": constraints,
        "guidelines": guidelines,
        "depends_on": depends_on if isinstance(depends_on, str) else None,
        "props": project_properties(value.get("props")),
        "links": project_links(value.get("links")),
    }


def project_control(control: Mapping[str, Any]) -> dict[str, Any]:
    """Project one control without its nested controls, which are listed separately."""
    parameters = [project_parameter(item) for item in _mappings(control.get("params"))]
    return {
        "class": _text(control.get("class")),
        "params": [item for item in parameters if item is not None],
        "props": project_properties(control.get("props")),
        "links": project_links(control.get("links")),
        "parts": [project_part(item) for item in _mappings(control.get("parts"))],
    }


def collect_link_resource_ids(projection: Mapping[str, Any]) -> list[str]:
    """Find back-matter resource UUIDs (`#<uuid>` links) referenced by a projected control."""
    found: list[str] = []

    def add_links(links: Sequence[Mapping[str, Any]]) -> None:
        for link in links:
            href = link["href"]
            if href.startswith("#") and len(href) > 1 and href[1:] not in found:
                found.append(href[1:])

    def visit_part(part: Mapping[str, Any]) -> None:
        add_links(part["links"])
        for child in part["parts"]:
            visit_part(child)

    add_links(projection["links"])
    for parameter in projection["params"]:
        add_links(parameter["links"])
    for part in projection["parts"]:
        visit_part(part)
    return found


def project_resource(value: Mapping[str, Any]) -> dict[str, Any] | None:
    identifier = _text(value.get("uuid"))
    if identifier is None:
        return None
    citation = value.get("citation")
    rlinks = [
        {"href": link["href"], "media_type": link["media_type"]}
        for link in project_links(value.get("rlinks"))
    ]
    return {
        "uuid": identifier,
        "title": _text(value.get("title")),
        "description": _text(value.get("description")),
        "citation": _text(citation.get("text")) if isinstance(citation, Mapping) else None,
        "rlinks": rlinks,
    }
