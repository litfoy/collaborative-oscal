import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class GroupProjection:
    oscal_group_id: str | None
    parent_path: str | None
    structural_path: str
    title: str
    display_order: int


@dataclass(frozen=True, slots=True)
class ControlProjection:
    oscal_control_id: str
    parent_path: str | None
    group_path: str | None
    title: str
    structural_path: str
    display_order: int


def canonical_json_sha256(document: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        document,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def project_catalog_indexes(
    document: Mapping[str, Any],
) -> tuple[list[GroupProjection], list[ControlProjection]]:
    """Build query projections without modifying or validating the source document."""
    catalog = document.get("catalog")
    if not isinstance(catalog, Mapping):
        raise ValueError("OSCAL document must contain a catalog object.")

    groups: list[GroupProjection] = []
    controls: list[ControlProjection] = []

    def visit_controls(
        values: Any,
        path: str,
        group_path: str | None,
        parent_path: str | None = None,
    ) -> None:
        if values is None:
            return
        if not isinstance(values, list):
            raise ValueError(f"Expected a list of controls at {path}.")
        for order, control in enumerate(values):
            if not isinstance(control, Mapping):
                raise ValueError(f"Expected a control object at {path}/{order}.")
            oscal_id = control.get("id")
            title = control.get("title")
            if not isinstance(oscal_id, str) or not oscal_id:
                raise ValueError(f"Control at {path}/{order} has no OSCAL identifier.")
            if not isinstance(title, str):
                raise ValueError(f"Control {oscal_id} has no title.")
            control_path = f"{path}/controls/{order}"
            controls.append(
                ControlProjection(
                    oscal_control_id=oscal_id,
                    parent_path=parent_path,
                    group_path=group_path,
                    title=title,
                    structural_path=control_path,
                    display_order=order,
                )
            )
            visit_controls(control.get("controls"), control_path, group_path, control_path)

    def visit_groups(
        values: Any, path: str, parent_path: str | None = None
    ) -> None:
        if values is None:
            return
        if not isinstance(values, list):
            raise ValueError(f"Expected a list of groups at {path}.")
        for order, group in enumerate(values):
            if not isinstance(group, Mapping):
                raise ValueError(f"Expected a group object at {path}/{order}.")
            title = group.get("title")
            oscal_id = group.get("id")
            if not isinstance(title, str):
                raise ValueError(f"Group at {path}/{order} has no title.")
            if oscal_id is not None and not isinstance(oscal_id, str):
                raise ValueError(f"Group at {path}/{order} has an invalid OSCAL identifier.")
            group_path = f"{path}/groups/{order}"
            groups.append(
                GroupProjection(
                    oscal_group_id=oscal_id,
                    parent_path=parent_path,
                    structural_path=group_path,
                    title=title,
                    display_order=order,
                )
            )
            visit_controls(group.get("controls"), group_path, group_path)
            visit_groups(group.get("groups"), group_path, group_path)

    visit_controls(catalog.get("controls"), "/catalog", None)
    visit_groups(catalog.get("groups"), "/catalog")
    return groups, controls


def document_metadata(document: Mapping[str, Any]) -> tuple[UUID, str]:
    catalog = document.get("catalog")
    if not isinstance(catalog, Mapping):
        raise ValueError("OSCAL document must contain a catalog object.")
    document_uuid = catalog.get("uuid")
    metadata = catalog.get("metadata")
    if not isinstance(document_uuid, str) or not isinstance(metadata, Mapping):
        raise ValueError("OSCAL catalog UUID and metadata are required.")
    oscal_version = metadata.get("oscal-version")
    if not isinstance(oscal_version, str) or not oscal_version:
        raise ValueError("OSCAL metadata must contain oscal-version.")
    try:
        return UUID(document_uuid), oscal_version
    except ValueError as error:
        raise ValueError("OSCAL catalog UUID must be a valid UUID.") from error
