from __future__ import annotations

import argparse
import re
from pathlib import Path

import fitz


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "datafiles-PDF" / "40K_Core_Rules.pdf"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "datafiles-WH40K" / "40K_Core_Rules.md"

CHAPTER_TITLES = {
    "INTRODUCTION",
    "BASIC RULES",
    "CORE CONCEPTS",
    "DATASHEETS",
    "MOVING",
    "MAKING ATTACKS",
    "ATTACK SEQUENCE",
    "OTHER CONCEPTS",
    "THE BATTLE ROUND",
    "COMMAND PHASE",
    "MOVEMENT PHASE",
    "SHOOTING PHASE",
    "CHARGE PHASE",
    "FIGHT PHASE",
    "BATTLEFIELDS AND TACTICS",
    "TERRAIN",
    "OBJECTIVES",
    "STRATAGEMS",
    "ACTIONS",
    "ADVANCED RULES",
    "MONSTERS AND VEHICLES",
    "TRANSPORTS",
    "ATTACHED UNITS",
    "STRATEGIC RESERVES",
    "FLYING AND SURGING",
    "OTHER RULES AND ABILITIES",
    "AIRCRAFT",
    "REFERENCE",
    "CORE ABILITIES",
    "RULES APPENDIX",
    "CORE RULES INDEX",
}

CHAPTER_NUMBERS = {f"{n:02d}" for n in range(1, 25)}

TRANSLATION_TABLE = str.maketrans(
    {
        "\x08": " ",
        "\uf0a7": "-",
        "\u25aa": "-",
        "\u25ab": "-",
        "\u25ba": ">",
        "\u0007": "",
        "\ufffd": "",
        "\u2011": "-",
        "\u2010": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u00bd": "1/2",
    }
)


def clean_text(text: str) -> str:
    text = text.translate(TRANSLATION_TABLE)
    text = re.sub(r"[\u200b-\u200f\u202a-\u202e]", "", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.replace(" ,", ",").replace(" .", ".").replace(" :", ":")
    return text.strip()


def normalise_heading(text: str) -> str:
    text = clean_text(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" -").upper()


def is_upper_heading(line: str) -> bool:
    letters = re.sub(r"[^A-Za-z]", "", line)
    if len(letters) < 4:
        return False
    return letters.upper() == letters


def merge_heading_lines(lines: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
        if normalise_heading(line) in CHAPTER_TITLES:
            out.append(line)
            i += 1
            continue
        if next_line and re.fullmatch(r"\d{2}\.\d{2}", next_line):
            out.append(f"{line} {next_line}")
            i += 2
            continue
        if (
            next_line
            and is_upper_heading(line)
            and is_upper_heading(next_line)
            and re.search(r"\b\d{2}\.\d{2}\b$", next_line)
        ):
            out.append(f"{line} {next_line}")
            i += 2
            continue
        out.append(line)
        i += 1
    return out


def render_line(line: str, emitted_chapters: set[str]) -> str | None:
    line = clean_text(line)
    if not line:
        return None
    line = re.sub(
        r"^(?:FAILS|HIT|WOUND|CRITICAL HIT|CRITICAL WOUND)\s+(?=\d+\.\s+[A-Z])",
        "",
        line,
    )
    if re.fullmatch(r"\d{1,2}", line) and line in CHAPTER_NUMBERS:
        return None

    heading = normalise_heading(line)
    if heading in CHAPTER_TITLES and heading not in emitted_chapters:
        emitted_chapters.add(heading)
        return f"## {heading.title()}"

    match = re.match(r"^(.*?)\s+(\d{2}\.\d{2})$", line)
    if match and is_upper_heading(match.group(1)):
        raw_name = match.group(1).strip()
        if raw_name.startswith(("++", "►")) or "[" in raw_name:
            return line
        name = normalise_heading(match.group(1)).title()
        return f"#### {name} {match.group(2)}"

    if line.startswith("- "):
        return line

    return line


def page_to_markdown(text: str, page_number: int, emitted_chapters: set[str]) -> list[str]:
    cleaned = clean_text(text)
    lines = merge_heading_lines([line for line in cleaned.splitlines() if line.strip()])
    if lines and lines[-1] == str(page_number):
        lines = lines[:-1]

    rendered = [f"### Page {page_number}"]
    for line in lines:
        item = render_line(line, emitted_chapters)
        if item:
            rendered.append(item)
    return rendered


def convert_pdf(pdf_path: Path) -> str:
    pdf_path = pdf_path.resolve()
    source_path = pdf_path.relative_to(PROJECT_ROOT).as_posix()
    document = fitz.open(pdf_path)
    emitted_chapters: set[str] = set()
    sections = [
        "# Warhammer 40,000 - Core Rules (11th Edition)",
        "",
        f"Source PDF: {source_path}",
    ]

    for page_number, page in enumerate(document, start=1):
        text = page.get_text() or ""
        if not text.strip():
            continue
        page_lines = page_to_markdown(text, page_number, emitted_chapters)
        sections.extend(["", *page_lines])

    return "\n".join(sections).strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    markdown = convert_pdf(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(markdown, encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
