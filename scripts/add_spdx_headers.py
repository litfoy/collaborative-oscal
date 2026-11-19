# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

from pathlib import Path

RULES = {
    ".py": [
        "# SPDX-License-Identifier: Apache-2.0",
        "# Copyright The Collaborative OSCAL Authors.",
        "",
    ],
    ".ts": [
        "// SPDX-License-Identifier: Apache-2.0",
        "// Copyright The Collaborative OSCAL Authors.",
        "",
    ],
    ".tsx": [
        "// SPDX-License-Identifier: Apache-2.0",
        "// Copyright The Collaborative OSCAL Authors.",
        "",
    ],
}

ROOTS = [
    Path("apps/api/app"),
    Path("apps/api/tests"),
    Path("apps/web/src"),
    Path("apps/web/tests"),
    Path("packages/oscal/src/collaborative_oscal_oscal"),
]


def main() -> None:
    updated: list[str] = []
    for root in ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in RULES:
                continue
            if "__pycache__" in path.parts:
                continue

            text = path.read_text(encoding="utf-8")
            if "SPDX-License-Identifier:" in "\n".join(text.splitlines()[:10]):
                continue

            header = "\n".join(RULES[path.suffix]) + "\n"
            path.write_text(header + text, encoding="utf-8")
            updated.append(path.as_posix())

    print(f"Updated {len(updated)} files")


if __name__ == "__main__":
    main()


