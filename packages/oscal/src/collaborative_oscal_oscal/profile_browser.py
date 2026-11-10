"""Compact, read-only presentation index for selecting controls from a catalog."""

from typing import Any

from collaborative_oscal_oscal.control_view import project_properties


def project_profile_browser(document: dict[str, Any]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []

    def content(value: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
        text = [
            value[key]
            for key in ("title", "prose", "label", "usage", "description")
            if isinstance(value.get(key), str)
        ]
        text.extend(value.get("values", []))
        properties = project_properties(value.get("props"))
        for key in ("parts", "params"):
            for child in value.get(key, []):
                child_text, child_properties = content(child)
                text.extend(child_text)
                properties.extend(child_properties)
        return text, properties

    def visit(value: dict[str, Any], parent: str | None, path: str) -> None:
        for collection, kind in (("controls", "control"), ("groups", "group")):
            for index, child in enumerate(value.get(collection, [])):
                key = f"{path}/{collection}/{index}"
                text, properties = content(child)
                nodes.append(
                    {
                        "key": key,
                        "parent_key": parent,
                        "kind": kind,
                        "id": child.get("id"),
                        "title": child["title"],
                        "text": "\n".join(text),
                        "properties": properties,
                    }
                )
                visit(child, key, key)

    visit(document["catalog"], None, "/catalog")
    return nodes
