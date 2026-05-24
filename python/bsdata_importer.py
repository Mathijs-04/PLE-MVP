"""
Convert BSData BattleScribe catalogues (.cat XML) to faction markdown files.

Fetches catalogues from the BSData GitHub repositories and writes markdown
to data/datafiles-WH40K/ and data/datafiles-WHAOS/. Used by
update_rules_from_bsdata.py for the full import-and-index workflow.

See docs/data.md for folder layout, markdown format, and pipeline commands.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable


BS_NS = {"bs": "http://www.battlescribe.net/schema/catalogueSchema"}
MANIFEST_PATH = Path(__file__).resolve().parent.parent / "data" / "bsdata-import-manifest.json"

REPOS = {
    "wh40k": {
        "repo": "BSData/wh40k-10e",
        "data_dir": Path(__file__).resolve().parent.parent / "data" / "datafiles-WH40K",
    },
    "aos": {
        "repo": "BSData/age-of-sigmar-4th",
        "data_dir": Path(__file__).resolve().parent.parent / "data" / "datafiles-WHAOS",
    },
}

PROTECTED_MARKDOWN = {
    "wh40k": {"40K_Core_Rules.md"},
    "aos": {
        "AOS_Core_Rules.md",
        "Lores.md",
        "Regiments of Renown.md",
        "Path to Glory - Ascension.md",
        "Path to Glory - Blighted Wilds.md",
        "Path to Glory - Ravaged Coast.md",
    },
}


@dataclass
class SourceFile:
    name: str
    path: str
    sha: str
    download_url: str
    local_path: Path


@dataclass
class CatalogDocument:
    source: SourceFile
    root: ET.Element
    faction: str
    catalog_label: str | None = None


@dataclass
class UnitData:
    name: str
    points: int
    stats: dict[str, str]
    keywords: list[str]
    weapons: list[dict[str, str]]
    abilities: list[tuple[str, str, dict[str, str]]]


@dataclass
class RuleData:
    section: str
    name: str
    profile_type: str
    characteristics: dict[str, str]


@dataclass
class GeneratedFaction:
    faction: str
    filename: str
    markdown: str
    sources: list[SourceFile] = field(default_factory=list)
    unit_count: int = 0


@dataclass
class ImportResult:
    game: str
    generated: list[GeneratedFaction]
    written: list[Path]
    preserved: list[str]
    skipped: list[str]
    source_count: int
    dry_run: bool


def fetch_cat_files(
    game: str,
    *,
    destination: Path,
    repo: str | None = None,
    limit_files: int | None = None,
) -> list[SourceFile]:
    repo_name = repo or REPOS[game]["repo"]
    api_url = f"https://api.github.com/repos/{repo_name}/contents/"
    data = _http_json(api_url)
    cat_entries = [
        item
        for item in data
        if item.get("type") == "file"
        and item.get("name", "").lower().endswith(".cat")
        and item.get("download_url")
    ]
    cat_entries.sort(key=lambda item: item["name"].lower())
    if limit_files is not None:
        cat_entries = cat_entries[:limit_files]

    destination.mkdir(parents=True, exist_ok=True)
    source_files: list[SourceFile] = []
    for item in cat_entries:
        local_path = destination / _safe_filename(item["name"])
        _download_file(item["download_url"], local_path)
        source_files.append(
            SourceFile(
                name=item["name"],
                path=item["path"],
                sha=item.get("sha", ""),
                download_url=item["download_url"],
                local_path=local_path,
            )
        )
    return source_files


def load_catalogs(source_files: Iterable[SourceFile]) -> list[CatalogDocument]:
    source_files = list(source_files)
    base_factions = _base_factions_from_sources(source_files)
    documents: list[CatalogDocument] = []
    for source in source_files:
        root = ET.parse(source.local_path).getroot()
        faction, catalog_label = _catalog_identity_from_filename(source.name, base_factions)
        documents.append(
            CatalogDocument(
                source=source,
                root=root,
                faction=faction,
                catalog_label=catalog_label,
            )
        )
    return documents


def generate_markdown_for_game(game: str, documents: list[CatalogDocument]) -> list[GeneratedFaction]:
    index = _build_global_index(documents)
    grouped: dict[str, list[CatalogDocument]] = {}
    for document in documents:
        grouped.setdefault(document.faction, []).append(document)

    generated: list[GeneratedFaction] = []
    for faction in sorted(grouped):
        docs = sorted(grouped[faction], key=lambda doc: (doc.catalog_label is not None, doc.source.name.lower()))
        if game == "wh40k" and all(_is_library_source(doc.source.name) for doc in docs):
            continue
        units = _extract_units(game, docs, index)
        if not units:
            continue
        army_rules, subfaction_rules = _extract_rule_sections(game, docs)
        markdown = _render_faction_markdown(game, faction, army_rules, subfaction_rules, units)
        if validate_generated_markdown(markdown):
            generated.append(
                GeneratedFaction(
                    faction=faction,
                    filename=f"{_safe_filename(faction)}.md",
                    markdown=markdown,
                    sources=[doc.source for doc in docs],
                    unit_count=len(units),
                )
            )
    return generated


def import_game(
    game: str,
    *,
    dry_run: bool = False,
    skip_index: bool = False,
    limit_files: int | None = None,
    repo: str | None = None,
    data_dir: Path | None = None,
) -> ImportResult:
    target_dir = data_dir or REPOS[game]["data_dir"]
    with tempfile.TemporaryDirectory(prefix=f"bsdata-{game}-") as temp_name:
        temp_dir = Path(temp_name)
        sources = fetch_cat_files(game, destination=temp_dir / "cats", repo=repo, limit_files=limit_files)
        documents = load_catalogs(sources)
        generated = generate_markdown_for_game(game, documents)
        written, preserved, skipped = write_generated_markdown(
            game,
            generated,
            target_dir=target_dir,
            dry_run=dry_run,
        )
        if not dry_run:
            written_names = {path.name for path in written}
            manifest_generated = [faction for faction in generated if faction.filename in written_names]
            _write_manifest(game, repo or REPOS[game]["repo"], manifest_generated, sources)

        return ImportResult(
            game=game,
            generated=generated,
            written=written,
            preserved=preserved,
            skipped=skipped,
            source_count=len(sources),
            dry_run=dry_run,
        )


def write_generated_markdown(
    game: str,
    generated: list[GeneratedFaction],
    *,
    target_dir: Path,
    dry_run: bool,
) -> tuple[list[Path], list[str], list[str]]:
    written: list[Path] = []
    preserved: list[str] = []
    skipped: list[str] = []
    target_dir.mkdir(parents=True, exist_ok=True)

    for faction in generated:
        if faction.filename in PROTECTED_MARKDOWN.get(game, set()):
            skipped.append(faction.filename)
            continue
        destination = target_dir / faction.filename
        if dry_run:
            written.append(destination)
            continue
        destination.write_text(faction.markdown, encoding="utf-8", newline="\n")
        written.append(destination)

    existing = {path.name for path in target_dir.glob("*.md")}
    generated_names = {faction.filename for faction in generated}
    for filename in sorted(existing - generated_names):
        if filename in PROTECTED_MARKDOWN.get(game, set()) or filename.endswith(".md"):
            preserved.append(filename)

    return written, preserved, skipped


def validate_generated_markdown(markdown: str) -> bool:
    if not re.search(r"^#\s+.+$", markdown, re.MULTILINE):
        return False
    if not re.search(r"^## Units\s*$", markdown, re.MULTILINE):
        return False
    if not re.search(r"^## Points Table\s*$", markdown, re.MULTILINE):
        return False
    unit_blocks = re.split(r"^###\s+", markdown, flags=re.MULTILINE)[1:]
    valid_units = 0
    for block in unit_blocks:
        if re.search(r"^\*\*Points:\*\*\s*\d+", block[:400], re.MULTILINE) and re.search(
            r"^\*\*Keywords:\*\*\s*.+$", block[:500], re.MULTILINE
        ):
            valid_units += 1
    return valid_units > 0


def _build_global_index(documents: list[CatalogDocument]) -> dict[str, ET.Element]:
    index: dict[str, ET.Element] = {}
    for document in documents:
        for element in document.root.findall(".//bs:selectionEntry", BS_NS):
            if element_id := element.get("id"):
                index[element_id] = element
        for element in document.root.findall(".//bs:sharedSelectionEntry", BS_NS):
            if element_id := element.get("id"):
                index[element_id] = element
        for element in document.root.findall(".//bs:profile", BS_NS):
            if element_id := element.get("id"):
                index[element_id] = element
        for element in document.root.findall(".//bs:sharedProfile", BS_NS):
            if element_id := element.get("id"):
                index[element_id] = element
    return index


def _extract_units(game: str, docs: list[CatalogDocument], index: dict[str, ET.Element]) -> list[UnitData]:
    units: dict[str, UnitData] = {}
    for document in docs:
        entries = list(document.root.findall(".//bs:selectionEntry", BS_NS))
        entries.extend(document.root.findall(".//bs:sharedSelectionEntry", BS_NS))
        entries.extend(document.root.findall(".//bs:entryLink", BS_NS))
        for entry in entries:
            resolved = _resolve_entry(entry, index)
            if resolved is None:
                continue
            unit = _unit_from_entry(game, entry, resolved, index, document.faction)
            if unit is None:
                continue
            units.setdefault(unit.name, unit)
    return sorted(units.values(), key=lambda unit: unit.name.lower())


def _unit_from_entry(
    game: str,
    original: ET.Element,
    entry: ET.Element,
    index: dict[str, ET.Element],
    faction: str,
) -> UnitData | None:
    entry_type = (entry.get("type") or original.get("type") or "").lower()
    if entry_type not in {"model", "unit"}:
        return None

    profiles = _profiles_for_entry(entry, index)
    if original is not entry:
        profiles.extend(_profiles_for_entry(original, index))

    unit_profiles = [profile for profile in profiles if _profile_type(profile).lower() == "unit"]
    if not unit_profiles:
        return None

    points = _points_for_entry(original) or _points_for_entry(entry)
    if points is None:
        return None

    name = _clean_text(original.get("name") or entry.get("name") or unit_profiles[0].get("name") or "")
    if not name or _is_option_name(name):
        return None

    stats = _characteristics(unit_profiles[0])
    keywords = _keywords_for_entry(original, entry, faction)
    weapons = _weapon_profiles(game, profiles)
    abilities = _ability_profiles(profiles)

    return UnitData(
        name=name,
        points=points,
        stats=stats,
        keywords=keywords,
        weapons=weapons,
        abilities=abilities,
    )


def _profiles_for_entry(entry: ET.Element, index: dict[str, ET.Element]) -> list[ET.Element]:
    profiles = list(entry.findall(".//bs:profile", BS_NS))
    for link in entry.findall(".//bs:profileLink", BS_NS):
        target = index.get(link.get("targetId", ""))
        if target is not None:
            profiles.append(target)
    return profiles


def _resolve_entry(entry: ET.Element, index: dict[str, ET.Element]) -> ET.Element | None:
    if _local_name(entry.tag) != "entryLink":
        return entry
    return index.get(entry.get("targetId", ""))


def _points_for_entry(entry: ET.Element) -> int | None:
    for cost in entry.findall("./bs:costs/bs:cost", BS_NS):
        if (cost.get("name") or "").strip().lower() == "pts":
            value = cost.get("value", "")
            try:
                return int(float(value))
            except ValueError:
                return None
    return None


def _keywords_for_entry(original: ET.Element, entry: ET.Element, faction: str) -> list[str]:
    keywords: list[str] = []
    for source in (original, entry):
        for link in source.findall("./bs:categoryLinks/bs:categoryLink", BS_NS):
            name = _clean_text(link.get("name", ""))
            if not name:
                continue
            if name.lower() in {"configuration", "reference"}:
                continue
            if name.lower().startswith("faction:"):
                name = name.split(":", 1)[1].strip()
            keywords.append(name)
    if not keywords:
        keywords.append(faction)
    return _unique_clean(keywords)


def _weapon_profiles(game: str, profiles: list[ET.Element]) -> list[dict[str, str]]:
    weapons: list[dict[str, str]] = []
    for profile in profiles:
        profile_type = _profile_type(profile).lower()
        if "weapon" not in profile_type:
            continue
        characteristics = _characteristics(profile)
        if game == "wh40k":
            hit = characteristics.get("BS") or characteristics.get("WS") or "-"
            weapons.append(
                {
                    "Weapon": _clean_text(profile.get("name", "")),
                    "Type": "Melee" if "melee" in profile_type else "Ranged",
                    "Range": characteristics.get("Range", "Melee" if "melee" in profile_type else "-"),
                    "A": characteristics.get("A", "-"),
                    "BS/WS": hit,
                    "S": characteristics.get("S", "-"),
                    "AP": characteristics.get("AP", "-"),
                    "D": characteristics.get("D", "-"),
                    "Keywords": characteristics.get("Keywords", "-"),
                }
            )
        else:
            weapons.append(
                {
                    "Weapon": _clean_text(profile.get("name", "")),
                    "Type": "Melee" if "melee" in profile_type else "Ranged",
                    "Rng": characteristics.get("Rng") or characteristics.get("Range") or ("-" if "melee" in profile_type else "-"),
                    "Atk": characteristics.get("Atk", "-"),
                    "Hit": characteristics.get("Hit", "-"),
                    "Wnd": characteristics.get("Wnd", "-"),
                    "Rnd": characteristics.get("Rnd", "-"),
                    "Dmg": characteristics.get("Dmg", "-"),
                    "Ability": characteristics.get("Ability", "-"),
                }
            )
    return [weapon for weapon in weapons if weapon["Weapon"]]


def _ability_profiles(profiles: list[ET.Element]) -> list[tuple[str, str, dict[str, str]]]:
    abilities: list[tuple[str, str, dict[str, str]]] = []
    for profile in profiles:
        profile_type = _profile_type(profile)
        if "ability" not in profile_type.lower() and profile_type.lower() != "abilities":
            continue
        name = _clean_text(profile.get("name", ""))
        if not name:
            continue
        characteristics = _characteristics(profile)
        abilities.append((name, profile_type, characteristics))
    return abilities


def _iter_rule_entries(game: str, root: ET.Element) -> Iterable[tuple[ET.Element, str]]:
    if game == "aos":
        containers = [
            root.find("./bs:selectionEntries", BS_NS),
            root.find("./bs:sharedSelectionEntries", BS_NS),
            root.find("./bs:sharedSelectionEntryGroups", BS_NS),
        ]
        for container in containers:
            if container is not None:
                yield from _iter_rule_entries_in_container(container, None)
        return

    for path in ("./bs:selectionEntries", "./bs:sharedSelectionEntries"):
        container = root.find(path, BS_NS)
        if container is not None:
            for child in list(container):
                if _is_entry_element(child):
                    section = _section_from_name(child.get("name", ""), None)
                    yield child, section


def _iter_rule_entries_in_container(container: ET.Element, section: str | None) -> Iterable[tuple[ET.Element, str]]:
    for child in list(container):
        if _is_entry_element(child):
            entry_section = _section_from_name(child.get("name", ""), section)
            yield child, entry_section
            for nested_container_name in ("selectionEntryGroups", "selectionEntries", "sharedSelectionEntries"):
                nested = child.find(f"./bs:{nested_container_name}", BS_NS)
                if nested is not None:
                    yield from _iter_rule_entries_in_container(nested, entry_section)
        elif _local_name(child.tag) == "selectionEntryGroup":
            group_section = _section_from_name(child.get("name", ""), section)
            yield from _iter_rule_entries_in_container(child, group_section)
        elif _local_name(child.tag) in {"selectionEntries", "sharedSelectionEntries", "selectionEntryGroups"}:
            yield from _iter_rule_entries_in_container(child, section)


def _is_entry_element(element: ET.Element) -> bool:
    return _local_name(element.tag) in {"selectionEntry", "sharedSelectionEntry"}


def _section_from_name(name: str, fallback: str | None) -> str:
    clean = _clean_text(name)
    without_faction = clean.split(":", 1)[0].strip() if ":" in clean else clean
    lowered = without_faction.lower()
    mappings = [
        ("battle trait", "Battle Traits"),
        ("battle formation", "Battle Formations"),
        ("army of renown", "Armies of Renown"),
        ("artefact", "Artefacts of Power"),
        ("artifact", "Artefacts of Power"),
        ("heroic trait", "Heroic Traits"),
        ("command trait", "Heroic Traits"),
        ("spell lore", "Spell Lore"),
        ("prayer lore", "Prayer Lore"),
        ("manifestation lore", "Manifestation Lore"),
        ("manifestation", "Manifestation Lore"),
        ("regiment", "Regiments of Renown"),
    ]
    for needle, section in mappings:
        if needle in lowered:
            return section
    return fallback or without_faction or "Imported Rules"


def _is_useful_rule_profile(profile_type: str) -> bool:
    lowered = profile_type.lower()
    return any(token in lowered for token in ("ability", "spell", "prayer", "manifestation"))


def _has_rule_content(characteristics: dict[str, str]) -> bool:
    return any(value.strip() for key, value in characteristics.items() if key.lower() != "used by")


def _extract_rule_sections(
    game: str,
    docs: list[CatalogDocument],
) -> tuple[dict[str, list[RuleData]], dict[str, dict[str, list[RuleData]]]]:
    army_rules: dict[str, list[RuleData]] = {}
    subfaction_rules: dict[str, dict[str, list[RuleData]]] = {}
    seen: set[tuple[str, str, str, tuple[tuple[str, str], ...], str | None]] = set()
    for document in docs:
        rules = _extract_army_rules(game, document)
        if document.catalog_label:
            target = subfaction_rules.setdefault(document.catalog_label, {})
        else:
            target = army_rules
        for rule in rules:
            key = (
                rule.section,
                rule.name,
                rule.profile_type,
                tuple(sorted(rule.characteristics.items())),
                document.catalog_label,
            )
            if key in seen:
                continue
            seen.add(key)
            target.setdefault(rule.section, []).append(rule)
    return army_rules, subfaction_rules


def _extract_army_rules(game: str, document: CatalogDocument) -> list[RuleData]:
    rules: list[RuleData] = []
    for entry, section in _iter_rule_entries(game, document.root):
        entry_type = (entry.get("type") or "").lower()
        if entry_type in {"model", "unit"}:
            continue
        for profile in entry.findall("./bs:profiles/bs:profile", BS_NS):
            profile_type = _profile_type(profile)
            if not _is_useful_rule_profile(profile_type):
                continue
            name = _clean_text(profile.get("name", ""))
            characteristics = _characteristics(profile)
            if name and _has_rule_content(characteristics):
                rules.append(
                    RuleData(
                        section=section or "Imported Rules",
                        name=name,
                        profile_type=profile_type,
                        characteristics=characteristics,
                    )
                )
    return rules


def _render_faction_markdown(
    game: str,
    faction: str,
    army_rules: dict[str, list[RuleData]],
    subfaction_rules: dict[str, dict[str, list[RuleData]]],
    units: list[UnitData],
) -> str:
    lines = [f"# {faction}", ""]
    if army_rules:
        lines.extend(["## Army Rules", ""])
        for section, rules in army_rules.items():
            lines.extend([f"### {section}", ""])
            for rule in rules:
                lines.extend(_render_rule(rule))
                lines.append("")

    if subfaction_rules:
        lines.extend(["## Subfactions", ""])
        for label in sorted(subfaction_rules):
            lines.extend([f"### {label}", ""])
            for section, rules in subfaction_rules[label].items():
                if section != "Imported Rules" and section != label:
                    lines.extend([f"**{section}**", ""])
                for rule in rules:
                    lines.extend(_render_rule(rule))
                    lines.append("")

    lines.extend(["## Units", ""])
    for unit in units:
        lines.extend(_render_unit(game, unit))
        lines.extend(["---", ""])

    lines.extend(_render_points_table(units))
    return "\n".join(lines).rstrip() + "\n"


def _render_rule(rule: RuleData) -> list[str]:
    return _render_ability(rule.name, rule.profile_type, rule.characteristics)


def _render_unit(game: str, unit: UnitData) -> list[str]:
    stat_line = _unit_stat_line(game, unit)
    lines = [
        f"### {unit.name}",
        stat_line,
        f"**Keywords:** {', '.join(unit.keywords)}",
        "",
    ]
    if unit.weapons:
        headers = (
            ["Weapon", "Type", "Range", "A", "BS/WS", "S", "AP", "D", "Keywords"]
            if game == "wh40k"
            else ["Weapon", "Type", "Rng", "Atk", "Hit", "Wnd", "Rnd", "Dmg", "Ability"]
        )
        lines.extend(["**Weapons:**", _markdown_table(headers, unit.weapons), ""])
    if unit.abilities:
        lines.extend(["**Abilities:**", ""])
        for name, profile_type, characteristics in unit.abilities:
            lines.extend(_render_ability(name, profile_type, characteristics))
            lines.append("")
    return lines


def _unit_stat_line(game: str, unit: UnitData) -> str:
    if game == "wh40k":
        fields = [
            ("M", unit.stats.get("M", "-")),
            ("T", unit.stats.get("T", "-")),
            ("SV", unit.stats.get("SV", "-")),
            ("W", unit.stats.get("W", "-")),
            ("LD", unit.stats.get("LD", "-")),
            ("OC", unit.stats.get("OC", "-")),
        ]
    else:
        fields = [
            ("Move", unit.stats.get("Move", "-")),
            ("Health", unit.stats.get("Health", "-")),
            ("Save", unit.stats.get("Save", "-")),
            ("Control", unit.stats.get("Control", "-")),
        ]
    parts = [f"**Points:** {unit.points}"]
    parts.extend(f"**{key}:** {value}" for key, value in fields)
    return " | ".join(parts)


def _render_ability(name: str, profile_type: str, characteristics: dict[str, str]) -> list[str]:
    kind = profile_type.replace("Ability", "").strip() or "Ability"
    kind = kind.strip("() ") or "Ability"
    lines = [f"#### {name} ({kind})"]
    if "Description" in characteristics:
        lines.append(f"- **Description:** {characteristics['Description']}")
        return lines
    for key, value in characteristics.items():
        if key.lower() == "used by" or value == "":
            continue
        lines.append(f"- **{key}:** {value}")
    return lines


def _render_points_table(units: list[UnitData]) -> list[str]:
    lines = ["## Points Table", "", "| Unit | Points |", "| --- | ---: |"]
    for unit in sorted(units, key=lambda item: (item.points, item.name.lower())):
        lines.append(f"| {_escape_table(unit.name)} | {unit.points} |")
    return lines


def _markdown_table(headers: list[str], rows: list[dict[str, str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("-" * (len(header) + 2) for header in headers) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_escape_table(row.get(header, "-")) for header in headers) + " |")
    return "\n".join(lines)


def _characteristics(profile: ET.Element) -> dict[str, str]:
    values: dict[str, str] = {}
    for characteristic in profile.findall(".//bs:characteristic", BS_NS):
        name = _clean_text(characteristic.get("name", ""))
        value = _clean_text(characteristic.text or "")
        if name:
            values[name] = value
    return values


def _profile_type(profile: ET.Element) -> str:
    return _clean_text(profile.get("typeName") or profile.get("type") or "")


def _write_manifest(
    game: str,
    repo: str,
    generated: list[GeneratedFaction],
    sources: list[SourceFile],
    *,
    manifest_path: Path = MANIFEST_PATH,
) -> None:
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {"version": 1, "games": {}}
    manifest["generated_at"] = datetime.now(UTC).isoformat()
    manifest.setdefault("games", {})[game] = {
        "repo": repo,
        "source_files": {source.path: source.sha for source in sources},
        "generated_files": [faction.filename for faction in generated],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _base_factions_from_sources(source_files: Iterable[SourceFile]) -> set[str]:
    base_factions: set[str] = set()
    for source in source_files:
        stem = Path(source.name).stem
        parts = [part.strip() for part in stem.split(" - ") if part.strip()]
        if len(parts) == 1:
            base_factions.add(parts[0])
        elif parts[-1].lower() == "library":
            base_factions.add(" - ".join(parts[:-1]))
    return base_factions


def _catalog_identity_from_filename(filename: str, base_factions: set[str]) -> tuple[str, str | None]:
    stem = Path(filename).stem
    parts = [part.strip() for part in stem.split(" - ") if part.strip()]
    if len(parts) > 1 and parts[-1].lower() == "library":
        return " - ".join(parts[:-1]), None
    if len(parts) > 1 and parts[0].lower() in {"imperium", "chaos", "aeldari"}:
        return parts[-1], None
    if len(parts) > 1 and parts[0] in base_factions:
        return parts[0], " - ".join(parts[1:])
    return stem, None


def _is_library_source(filename: str) -> bool:
    stem = Path(filename).stem.lower()
    return "library" in stem


def _safe_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip().rstrip(".")


def _is_option_name(name: str) -> bool:
    lowered = name.lower()
    return lowered in {"warlord", "show/hide options", "order of battle", "detachment"}


def _clean_text(value: str) -> str:
    value = value.replace("\u00a0", " ").replace("\u200e", "").replace("�", "'")
    value = re.sub(r"\*\*\^\^(.+?)\^\^\*\*", r"\1", value)
    value = re.sub(r"\^\^(.+?)\^\^", r"\1", value)
    value = re.sub(r"\*\*\^\^([^*\n]+)", r"\1", value)
    value = re.sub(r"\^\^([^*\n]+)", r"\1", value)
    value = re.sub(r"\^\^\*\*", "", value)
    value = re.sub(r"[ \t\r\f\v]+", " ", value)
    value = re.sub(r"\n\s+", "\n", value)
    return value.strip()


def _unique_clean(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = _clean_text(value)
        if clean and clean.lower() not in seen:
            seen.add(clean.lower())
            result.append(clean)
    return result


def _escape_table(value: str) -> str:
    return _clean_text(str(value)).replace("|", r"\|") or "-"


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _http_json(url: str) -> list[dict[str, object]]:
    request = urllib.request.Request(url, headers={"User-Agent": "Warhammer-Rule-Assistant"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _download_file(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "Warhammer-Rule-Assistant"})
    with urllib.request.urlopen(request, timeout=120) as response:
        with destination.open("wb") as handle:
            shutil.copyfileobj(response, handle)


def import_from_local_cat_files(
    game: str,
    cat_paths: Iterable[Path],
    *,
    data_dir: Path,
    dry_run: bool = True,
) -> ImportResult:
    sources = [
        SourceFile(
            name=path.name,
            path=path.name,
            sha="local",
            download_url=urllib.parse.urljoin("file:", str(path)),
            local_path=path,
        )
        for path in cat_paths
    ]
    documents = load_catalogs(sources)
    generated = generate_markdown_for_game(game, documents)
    written, preserved, skipped = write_generated_markdown(
        game,
        generated,
        target_dir=data_dir,
        dry_run=dry_run,
    )
    return ImportResult(
        game=game,
        generated=generated,
        written=written,
        preserved=preserved,
        skipped=skipped,
        source_count=len(sources),
        dry_run=dry_run,
    )
