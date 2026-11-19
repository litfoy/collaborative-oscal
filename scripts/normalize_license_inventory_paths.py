# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
INVENTORY_FILES = [
    REPO_ROOT / "docs" / "npm-license-inventory.json",
    REPO_ROOT / "docs" / "python-license-inventory.runtime.json",
    REPO_ROOT / "docs" / "python-license-inventory.dev-and-runtime.json",
]


def _normalize_path(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    if value in {"UNKNOWN", ""}:
        return value

    candidate = Path(value)
    try:
        return candidate.resolve().relative_to(REPO_ROOT).as_posix()
    except Exception:
        normalized = value.replace("\\", "/")
        for marker in ("/site-packages/", "/node_modules/"):
            if marker in normalized:
                tail = normalized.split(marker, maxsplit=1)[1]
                return f"{marker.strip('/')}/{tail}"
        return value


def normalize_npm_inventory(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    normalized: dict[str, Any] = {}

    for package_name in sorted(data):
        details = data[package_name]
        item = dict(details)
        if "path" in item:
            item["path"] = _normalize_path(item["path"])
        if "licenseFile" in item:
            item["licenseFile"] = _normalize_path(item["licenseFile"])
        normalized[package_name] = item

    path.write_text(json.dumps(normalized, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def normalize_python_inventory(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    normalized: list[dict[str, Any]] = []

    for row in data:
        item = dict(row)
        if "LicenseFile" in item:
            item["LicenseFile"] = _normalize_path(item["LicenseFile"])
        normalized.append(item)

    normalized.sort(key=lambda row: (str(row.get("Name", "")).lower(), str(row.get("Version", ""))))
    path.write_text(json.dumps(normalized, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def main() -> None:
    for file_path in INVENTORY_FILES:
        if file_path.name == "npm-license-inventory.json":
            normalize_npm_inventory(file_path)
        else:
            normalize_python_inventory(file_path)
        print(f"Normalized {file_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
