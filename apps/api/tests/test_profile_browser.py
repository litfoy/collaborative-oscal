import copy
import json
from pathlib import Path

from collaborative_oscal_oscal.profile_browser import project_profile_browser

from app.api.catalog_schemas import ProfileBrowserResponse


def test_actual_grundschutz_hierarchy_properties_and_source_text() -> None:
    source = Path(__file__).parents[3] / "examples/catalogs/Grundschutz++-resolved_catalog.json"
    document = json.loads(source.read_text())
    before = copy.deepcopy(document)
    nodes = ProfileBrowserResponse.model_validate(
        {"nodes": project_profile_browser(document)}
    ).model_dump()["nodes"]
    controls = [node for node in nodes if node["kind"] == "control"]
    groups = [node for node in nodes if node["kind"] == "group"]
    assert len(controls) == 1000
    assert len(groups) == 160
    first = next(node for node in controls if node["id"] == "GC.1.1")
    group = next(node for node in groups if node["key"] == first["parent_key"])
    assert group["id"] == "GC.1"
    assert next(node for node in groups if node["key"] == group["parent_key"])["id"] == "GC"
    properties = {prop["name"]: prop["value"] for prop in first["properties"]}
    assert properties["sec_level"] == "normal-SdT"
    assert properties["effort_level"] == "0"
    assert properties["modal_verb"] == "MUSS"  # sourced from a statement part
    assert "{{ insert: param, gc.1.1-prm1 }}" in first["text"]
    assert "Diese Anforderung ist der Ausgangs- und Endpunkt" in first["text"]
    assert document == before


def test_nested_controls_are_separate_and_extension_properties_are_not_assumed() -> None:
    document = {
        "catalog": {
            "controls": [
                {
                    "id": "Parent.ID",
                    "title": "Parent",
                    "params": [
                        {
                            "id": "p1",
                            "label": "Frequency",
                            "props": [
                                {"name": "custom", "ns": "urn:example", "value": "annual"},
                            ],
                        }
                    ],
                    "controls": [
                        {
                            "id": "Child.ID",
                            "title": "Child",
                            "parts": [
                                {"name": "statement", "prose": "Child-only text"},
                            ],
                        }
                    ],
                }
            ]
        }
    }
    nodes = project_profile_browser(document)
    assert [node["id"] for node in nodes] == ["Parent.ID", "Child.ID"]
    assert nodes[1]["parent_key"] == nodes[0]["key"]
    assert "Child-only text" not in nodes[0]["text"]
    assert nodes[0]["properties"][0]["ns"] == "urn:example"
    assert "Frequency" in nodes[0]["text"]
