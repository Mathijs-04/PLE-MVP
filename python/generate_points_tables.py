"""
Regenerate ## Points Table sections in faction markdown files.

Scans data/datafiles-WH40K/ and data/datafiles-WHAOS/, reads unit points from
each file's ## Units section, and writes or updates the ## Points Table section.

Usage:
    python generate_points_tables.py

See docs/data.md for the markdown format and data pipeline overview.
"""

import os
import re


HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)

AOS_DATA_DIR = os.path.join(PROJECT_ROOT, "data", "datafiles-WHAOS")
WH40K_DATA_DIR = os.path.join(PROJECT_ROOT, "data", "datafiles-WH40K")

SECTION_HEADER = "## Points Table"
SECTION_PATTERN = re.compile(
    r"\n## Points Table\n.*?\Z",
    re.DOTALL,
)
UNITS_SECTION_PATTERN = re.compile(
    r"^## Units\s*$([\s\S]+?)(?=^##\s+|\Z)",
    re.MULTILINE,
)
UNIT_HEADING_PATTERN = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)
POINTS_PATTERN = re.compile(r"^\*\*Points:\*\*\s*([0-9]+)", re.MULTILINE)

SKIP_AOS = {
    "AOS_Core_Rules.md",
    "Lores.md",
    "Regiments of Renown.md",
    "Path to Glory - Ascension.md",
    "Path to Glory - Blighted Wilds.md",
    "Path to Glory - Ravaged Coast.md",
}

SKIP_WH40K = {
    "40K_Core_Rules.md",
}


def iter_files(data_dir: str, skip: set[str]) -> list[str]:
    return [
        os.path.join(data_dir, name)
        for name in sorted(os.listdir(data_dir))
        if name.lower().endswith(".md") and name not in skip
    ]


def build_points_table(text: str) -> str:
    rows: list[tuple[str, int]] = []
    units_match = UNITS_SECTION_PATTERN.search(text)
    if not units_match:
        return ""

    units_text = units_match.group(1)
    headings = list(UNIT_HEADING_PATTERN.finditer(units_text))
    for index, heading in enumerate(headings):
        start = heading.start()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(units_text)
        section = units_text[start:end]
        points_match = POINTS_PATTERN.search(section[:400])
        if not points_match:
            continue
        rows.append((heading.group(1).strip(), int(points_match.group(1))))

    if not rows:
        return ""

    rows.sort(key=lambda item: (item[1], item[0].lower()))

    lines = [
        SECTION_HEADER,
        "",
        "| Unit | Points |",
        "| --- | ---: |",
    ]
    for unit_name, points in rows:
        safe_name = unit_name.replace("|", r"\|")
        lines.append(f"| {safe_name} | {points} |")
    return "\n".join(lines).rstrip() + "\n"


def update_file(path: str) -> bool:
    with open(path, "r", encoding="utf-8") as handle:
        original = handle.read().rstrip() + "\n"

    table = build_points_table(original)
    if not table:
        return False

    stripped = SECTION_PATTERN.sub("\n", original).rstrip() + "\n\n"
    updated = stripped + table

    if updated == original:
        return False

    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(updated)
    return True


def main() -> int:
    changed = 0
    total = 0

    for data_dir, skip in (
        (AOS_DATA_DIR, SKIP_AOS),
        (WH40K_DATA_DIR, SKIP_WH40K),
    ):
        for path in iter_files(data_dir, skip):
            total += 1
            if update_file(path):
                changed += 1
                print(f"updated: {path}")

    print(f"processed {total} faction files, changed {changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
