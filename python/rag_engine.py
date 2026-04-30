"""
Warhammer Rules RAG Engine.

Takes a FAISS vector index (built by build_index.py) and answers rules questions
using Retrieval-Augmented Generation (RAG) with an OpenAI chat model.

The retrieval pipeline combines two complementary strategies:
  1. Semantic (embedding) search via MMR for diverse, contextually relevant chunks.
  2. Keyword/structure-aware search that finds unit/ability headings by name,
     giving precise results for "how many points is X" or "what does ability Y do".

Usage (CLI / test mode):
    python rag_engine.py --game aos "Can I reinforce a Clanrats unit?"
    python rag_engine.py --game wh40k "What is the Devastating Wounds rule?"
    python rag_engine.py --game aos          # interactive REPL

Requires OPENAI_API_KEY in the environment or a .env file in the project root.
Built indexes must exist in python/indexes/. Run build_index.py first.
"""

import argparse
import difflib
import os
import re
import string
from typing import List, Optional, Sequence, Tuple

from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)

DEFAULT_WH40K_DATA_DIR = os.path.join(_PROJECT_ROOT, "data", "datafiles-WH40K")
DEFAULT_WH40K_INDEX_DIR = os.path.join(_HERE, "indexes", "40k")

DEFAULT_AOS_DATA_DIR = os.path.join(_PROJECT_ROOT, "data", "datafiles-WHAOS")
DEFAULT_AOS_INDEX_DIR = os.path.join(_HERE, "indexes", "aos")

EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_CHAT_MODEL = "gpt-5.4"

SYSTEM_PROMPT = """
You are a rules explainer for Warhammer tabletop games.

You answer questions ONLY using the provided rules text. DO NOT use any other information
or context. If the question is not related to the rules, say so.

Guidelines:
- If the rules text clearly answers the question, quote or closely paraphrase the relevant passages.
- When a specific rule or sentence from the provided context directly answers or is central to the
  question, include the literal rule text as a quote using markdown italics: *quoted rule text here*.
  Do NOT wrap quotes in double-quote characters — use only the italic markdown syntax.
  Only quote a rule when it is directly relevant to the answer; do not quote every rule or keyword
  you mention. Keep the overall answer concise.
- If the answer depends on definitions, sequences, or edge cases, walk through them step by step.
- When the general rules framework (phase order, sequencing, ability timing, fight order, etc.) is
  present in the context, answer confidently by applying that framework — even if the question also
  mentions a specific ability or unit whose exact text you don't have. Do NOT pad the answer with a
  list of things the context is missing; only flag a genuine gap when it materially changes the
  answer.
- If the context truly lacks the rule needed to answer, say so briefly in one sentence and stop.
- Do NOT reference page numbers unless they are explicitly present in the provided context.
- Be concise, but do not omit important conditions or exceptions.

When the user names a specific unit, ability, or keyword:
- Prioritise any context snippets that mention that exact name (case-insensitive).
- Pay particular attention to short "notes" sentences such as "This unit cannot be reinforced."
- If such a sentence is present in the context, treat it as authoritative for the question.

When the user asks for a recommendation or comparison across a faction (e.g. "best unit",
"strongest", "cheapest", "most powerful", "which unit should I take"):
- Use the unit-stats overview (if provided) to compare all available units.
- Clearly state the criterion you are applying (e.g. highest Points = most investment/power,
  highest Health = most durable, best Save = hardest to wound).
- Give a concrete, definitive recommendation — do not refuse on the grounds that
  the rules do not define "best". Make a reasoned pick and explain it.
- If multiple units are competitive, name the top two or three and briefly explain the trade-offs.

Assume the user is familiar with basic tabletop gaming, but not necessarily all Warhammer jargon.
Explain specialised terms briefly when they are important to the answer.

Always respond with a valid JSON object in exactly this format, and nothing else:

{
  "short_answer": "<one-line answer>",
  "detailed_answer": "<longer explanation with relevant conditions, edge cases, and literal rule quotes in *italics* where directly relevant>",
  "source": {
    "has_core_rules": <true if the answer draws on any core/universal rules, false otherwise>,
    "factions": ["<faction name as it appears in the rules, e.g. Skaven, Space Marines>"]
  },
  "certainty": <integer 1-4>
}

"certainty" indicates how confident you are that the answer is fully supported by the provided
rules context:
  1 = The answer is directly and completely supported by the rules text (including cases where
      the general framework in the core rules clearly resolves the question).
  2 = The answer is partially covered by the rules but requires some interpretation.
  3 = The rules barely address this, or relevant rules appear to contradict each other.
  4 = The rules do not cover this at all and you are guessing.
Do not lower certainty just because a specific named ability wasn't quoted in the context — if
the universal timing/sequencing/phase rules decide the outcome, that counts as certainty 1.

"has_core_rules" should be true whenever the answer references rules that apply to all players
(movement, combat sequence, keywords, universal abilities, etc.), not just faction-specific ones.
"factions" should list every faction whose specific rules (warscrolls, datasheets, army rules,
faction abilities) contributed to the answer. Use an empty array when no faction-specific rules
were needed.

Do not include any text outside the JSON object. Do not wrap it in code fences.
""".strip()

ARMY_LIST_SYSTEM_PROMPT = """
You are a Warhammer army-list builder. You will ALMOST ALWAYS receive a
pre-computed army list that already respects the requested points budget,
includes a centerpiece, reinforces battleline, and biases toward one
sub-faction for cohesion.

DEFAULT BEHAVIOUR — when a pre-computed list is present:
- Copy its bullet list and total into "detailed_answer" VERBATIM. Do not
  rename, swap, add, or remove any units. Do not recalculate totals.
- If an entry shows "(x2)" or "(x3)", keep it exactly like that.
- Preserve the order of the bullets.
- The only writing you do is a short explanation (2-3 sentences) of why
  the composition works.

WHEN NO PRE-COMPUTED LIST IS PROVIDED (rare fallback), build a list that:
- Has a centerpiece unit (~20-30% of the budget).
- Has 1-2 supporting heroes at mid-cost.
- Has 2-3 battleline/infantry units, with at least one taken twice.
- Has 1-2 heavier units (Monsters, Vehicles, War Machines).
- Optional: a support or ranged unit to fill out remaining points.
- Shares a sub-faction/keyword where possible for cohesion.
NEVER submit an army of only 2-3 elite monsters or only heroes — a real
army needs bodies on the board. NEVER submit an army of only the cheapest
datasheets either — include at least one expensive centerpiece.

STRICT OUTPUT RULES:
1. Return EXACTLY ONE recommended list. Never show rejected attempts,
   failed totals, or iterative recalculations.
2. "short_answer" is one sentence: the centerpiece, the theme (if any),
   and the total.
3. "detailed_answer" contains ONLY:
   - The unit list as bullet points ("- Unit Name (x2): 300 pts").
   - A "**Total: X/BUDGET points**" line.
   - 2-3 short sentences about why the composition works (centerpiece,
     core, support, shared sub-faction).
   - Nothing else. No alternative lists. No disclaimers about missing data.
4. The total MUST be at or below the requested budget. If you are copying
   a pre-computed list, the arithmetic is already correct — trust it.
5. Do NOT explain your reasoning process or show working.

Always respond with a valid JSON object in exactly this format, and nothing else:

{
  "short_answer": "<one-line summary>",
  "detailed_answer": "<bullet list + total + 2-3 sentences>",
  "source": {
    "has_core_rules": false,
    "factions": ["<faction name>"]
  },
  "certainty": 2
}

Do not include any text outside the JSON object. Do not wrap it in code fences.
""".strip()



def _extract_points_budget(question: str) -> Optional[int]:
    """
    Parse a points budget from the question. Accepts:
      - "1500 points", "1500 pts", "1500 pt", "1500-point", "1500point"
      - "1,500 points"
      - "2k", "2k points", "1.5k points"
      - "for 1500", "at 2000", "of 1500"
    Returns None when no budget is found.
    """
    q = question.lower()

    m = re.search(r"(\d[\d,]{2,5})\s*[-\s]?\s*(?:point|points|pts|pt)\b", q)
    if m:
        return int(m.group(1).replace(",", ""))

    m = re.search(r"\b(\d(?:\.\d)?)\s*k\s*(?:point|points|pts|pt)?\b", q)
    if m:
        return int(round(float(m.group(1)) * 1000))

    m = re.search(r"\b(?:for|at|of|with|around|about)\s+(\d[\d,]{2,5})\b", q)
    if m:
        val = int(m.group(1).replace(",", ""))
        if 250 <= val <= 10000:
            return val

    return None



_ROLE_KEYWORDS_AOS = {
    "hero": {"HERO"},
    "infantry": {"INFANTRY"},
    "monster": {"MONSTER"},
    "cavalry": {"CAVALRY"},
    "war_machine": {"WAR MACHINE"},
}

_ROLE_KEYWORDS_40K = {
    "hero": {"Character"},
    "infantry": {"Infantry"},
    "monster": {"Monster"},
    "vehicle": {"Vehicle"},
    "mounted": {"Mounted"},
}

_NON_THEME_KEYWORDS = frozenset({
    "HERO", "INFANTRY", "MONSTER", "CAVALRY", "WAR MACHINE",
    "VEHICLE", "CHARACTER", "BATTLELINE", "MOUNTED", "TITANIC",
    "CHAMPION", "VETERAN", "WARMASTER", "EPIC HERO", "UNIQUE",
    "WIZARD", "PRIEST", "WEAPON TEAM",
    "CHAOS", "ORDER", "DEATH", "DESTRUCTION",
    "IMPERIUM", "AELDARI", "TYRANIDS", "NECRONS", "ORK", "ORKS",
    "ASURYANI", "GENESTEALER CULTS",
    "FLY", "WARD", "DAEMON", "GRENADES", "LEGENDS",
    "MANIFESTATION", "ENDLESS SPELL", "FACTION TERRAIN",
    "INVOCATION", "REGIMENTS OF RENOWN",
    "IMPERIAL", "CHAOS KNIGHTS",
    "WALKER", "SMOKE", "TOWERING", "TRANSPORT", "AIRCRAFT",
    "HOVER", "DEEP STRIKE", "DEEP-STRIKE", "JUMP PACK", "SCOUT",
    "LONE OPERATIVE", "STEALTH", "FIRING DECK", "PSYKER",
    "SYNAPSE",  # universal Tyranids battlefield role, not a sub-faction
})

_UNIT_HEADING_RE = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)
_POINTS_LINE_RE = re.compile(r"\*\*Points:\*\*\s*(\d+)")
_KEYWORDS_LINE_RE = re.compile(r"^\*\*Keywords:\*\*\s*(.+)$", re.MULTILINE)


def _clean_keyword(kw: str) -> str:
    """Normalise a raw keyword token ("WIZARD (2)" -> "WIZARD")."""
    return re.sub(r"\s*\([^)]*\)", "", kw).strip().upper()


def _parse_units_with_roles(
    faction_text: str,
    game: str = "aos",
) -> list[dict]:
    units_match = re.search(
        r"^## Units\s*$([\s\S]+?)(?=^## (?!Units)|\Z)",
        faction_text,
        re.MULTILINE,
    )
    if not units_match:
        return []

    units_text = units_match.group(1)
    headings = list(_UNIT_HEADING_RE.finditer(units_text))
    role_map = _ROLE_KEYWORDS_40K if game == "wh40k" else _ROLE_KEYWORDS_AOS
    parsed: list[dict] = []

    for i, heading in enumerate(headings):
        start = heading.start()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(units_text)
        section = units_text[start:end]

        pts_m = _POINTS_LINE_RE.search(section[:400])
        if not pts_m:
            continue
        kw_m = _KEYWORDS_LINE_RE.search(section[:500])
        kw_text = kw_m.group(1) if kw_m else ""
        kw_upper = kw_text.upper()

        keywords = {_clean_keyword(tok) for tok in kw_text.split(",") if tok.strip()}
        keywords.discard("")

        if keywords & {"MANIFESTATION", "ENDLESS SPELL", "FACTION TERRAIN", "INVOCATION"}:
            continue

        roles: set[str] = set()
        for role, triggers in role_map.items():
            for trigger in triggers:
                if trigger.upper() in kw_upper:
                    roles.add(role)

        is_unique = "UNIQUE" in keywords or "EPIC HERO" in keywords
        is_battleline = "BATTLELINE" in keywords

        sub_factions = {kw for kw in keywords if kw not in _NON_THEME_KEYWORDS}

        parsed.append({
            "name": heading.group(1).strip(),
            "pts": int(pts_m.group(1)),
            "roles": roles,
            "unique": is_unique,
            "battleline": is_battleline,
            "keywords": keywords,
            "sub_factions": sub_factions,
        })

    return parsed



def _detect_theme_candidates(
    all_units: Sequence[dict],
    faction_name: str,
) -> list[tuple[str, int]]:
    """
    Rank candidate sub-faction keywords by how many units carry them, excluding
    keywords that essentially tag the whole faction (appear on >80% of units)
    or the faction name itself.
    """
    if not all_units:
        return []

    faction_toks = {t for t in re.split(r"[^A-Za-z]+", faction_name.upper()) if t}

    counts: dict[str, int] = {}
    for u in all_units:
        for kw in u.get("sub_factions", set()):
            if kw in faction_toks or len(kw) < 3:
                continue
            counts[kw] = counts.get(kw, 0) + 1

    total = len(all_units)
    ranked: list[tuple[str, int]] = []
    for kw, cnt in counts.items():
        if cnt < 2:
            continue
        if cnt / total > 0.80:
            continue
        ranked.append((kw, cnt))

    ranked.sort(key=lambda t: (-t[1], t[0]))
    return ranked


def _select_theme(
    question: str,
    theme_candidates: Sequence[tuple[str, int]],
) -> Optional[str]:
    """Pick a sub-faction theme, preferring one the user explicitly named."""
    if not theme_candidates:
        return None
    q_upper = question.upper()
    for kw, _cnt in theme_candidates:
        if kw in q_upper:
            return kw
    return theme_candidates[0][0]


def _user_requests_legends(question: str) -> bool:
    return bool(re.search(r"\b(?:legends?|legendary)\b", question, re.IGNORECASE))



def _budget_to_dupe_cap(budget: int) -> int:
    if budget < 750:
        return 1
    if budget < 1400:
        return 2
    if budget < 2500:
        return 3
    return 4


def _theme_bonus(unit: dict, theme: Optional[str]) -> int:
    if theme and theme in unit.get("sub_factions", set()):
        return 1
    return 0


def _build_army_list_from_table(
    faction_text: str,
    budget: int,
    game: str = "aos",
    question: str = "",
) -> Optional[str]:
    """
    Build a cohesive, budget-respecting army list.

    The picker works in tiers so the final list feels like a real army rather
    than a bag of cheapest units:

      1. Centerpiece   — one expensive themed hero/monster (~20-30% of budget).
      2. Support heroes — 1-2 mid-cost heroes that share the theme.
      3. Battleline    — 2-3 core infantry units, duplicated to form a backbone.
      4. Heavy support — 1-2 monsters/vehicles/war machines (not the cheapest).
      5. Auxiliary     — 0-2 support pieces (shooting, cavalry, specialists).
      6. Fill          — cheapest remaining picks until the remainder is too
                          small to matter.

    Theme detection keeps the army lorewise-cohesive (e.g. a Skaven list biases
    toward one of VERMINUS / PESTILENS / SKRYRE / ESHIN / MOULDER / MASTERCLAN).
    Duplication (`_budget_to_dupe_cap`) reflects how real armies field multiple
    Clanrats or Intercessor squads instead of one of every datasheet.
    """
    all_units = _parse_units_with_roles(faction_text, game)
    if not _user_requests_legends(question):
        all_units = [u for u in all_units if "LEGENDS" not in u["keywords"]]

    if not all_units:
        return None

    cheapest = min((u["pts"] for u in all_units), default=budget + 1)
    if cheapest > budget:
        return None

    faction_name = ""
    h1_m = re.match(r"^#\s+(.+)", faction_text)
    if h1_m:
        faction_name = h1_m.group(1).strip()
    theme_candidates = _detect_theme_candidates(all_units, faction_name)
    theme = _select_theme(question, theme_candidates)

    dupe_cap = _budget_to_dupe_cap(budget)

    def is_leader(u: dict) -> bool:
        return "hero" in u["roles"]

    def is_heavy(u: dict) -> bool:
        return (
            ("monster" in u["roles"] or "vehicle" in u["roles"]
             or "war_machine" in u["roles"])
            and not is_leader(u)
        )

    def is_infantry_core(u: dict) -> bool:
        return (
            ("infantry" in u["roles"] or u["battleline"])
            and not is_leader(u)
            and not u["unique"]
        )

    def is_support(u: dict) -> bool:
        return (
            not is_leader(u)
            and not is_heavy(u)
            and not is_infantry_core(u)
        )

    picks: list[dict] = []
    counts: dict[str, int] = {}
    remaining = budget

    def can_take(u: dict, extra_copies: int = 1) -> bool:
        if u["pts"] * extra_copies > remaining:
            return False
        if u["unique"] and counts.get(u["name"], 0) >= 1:
            return False
        if counts.get(u["name"], 0) + extra_copies > dupe_cap:
            return False
        return True

    def take(u: dict) -> bool:
        nonlocal remaining
        if not can_take(u):
            return False
        picks.append(u)
        counts[u["name"]] = counts.get(u["name"], 0) + 1
        remaining -= u["pts"]
        return True

    def take_one(pool: Sequence[dict], scorer) -> Optional[dict]:
        ranked = sorted(pool, key=scorer)
        for u in ranked:
            if can_take(u) and take(u):
                return u
        return None

    heroes = [u for u in all_units if is_leader(u) and not u["unique"]]
    epic_heroes = [u for u in all_units if is_leader(u) and u["unique"]]
    heavies = [u for u in all_units if is_heavy(u)]
    infantry_core = [u for u in all_units if is_infantry_core(u)]
    battleline = [u for u in infantry_core if u["battleline"]] or infantry_core
    support = [u for u in all_units if is_support(u)]

    centerpiece_min = budget * 0.14
    centerpiece_max = budget * 0.33
    centerpiece_pool = [
        u for u in (heroes + heavies + epic_heroes)
        if centerpiece_min <= u["pts"] <= centerpiece_max
    ]
    centerpiece_taken: Optional[dict] = None
    if budget >= 750 and centerpiece_pool:
        centerpiece_taken = take_one(
            centerpiece_pool,
            lambda u: (-_theme_bonus(u, theme), -u["pts"]),
        )

    support_hero_target = 2 if budget >= 1200 else 1
    support_hero_ideal = budget * 0.07
    taken_heroes = sum(1 for p in picks if is_leader(p))
    while taken_heroes < support_hero_target + (1 if centerpiece_taken and is_leader(centerpiece_taken) else 0):
        pool = [u for u in heroes if counts.get(u["name"], 0) == 0]
        if not pool:
            break
        picked = take_one(
            pool,
            lambda u: (
                -_theme_bonus(u, theme),
                abs(u["pts"] - support_hero_ideal),
            ),
        )
        if not picked:
            break
        taken_heroes += 1

    bl_target_units = 2 if budget < 1500 else 3
    bl_ideal = budget * 0.09
    bl_pool = sorted(
        battleline,
        key=lambda u: (-_theme_bonus(u, theme), abs(u["pts"] - bl_ideal), u["pts"]),
    )
    distinct_bl_picked = 0
    for u in bl_pool:
        if distinct_bl_picked >= bl_target_units:
            break
        if counts.get(u["name"], 0) > 0:
            continue
        if not take(u):
            continue
        distinct_bl_picked += 1
        bl_spend = sum(p["pts"] * counts[p["name"]] for p in picks if is_infantry_core(p))
        if bl_spend < budget * 0.35 and can_take(u):
            take(u)
        if bl_spend < budget * 0.25 and can_take(u):
            take(u)

    heavy_target = 2 if budget >= 1500 else 1
    heavies_taken = sum(
        1 for p in picks if is_heavy(p) and p is not centerpiece_taken
    )
    if centerpiece_taken is not None and is_heavy(centerpiece_taken):
        heavies_taken += 0  # centerpiece already counted separately
    heavy_ideal = budget * 0.11
    while heavies_taken < heavy_target:
        pool = [u for u in heavies if counts.get(u["name"], 0) == 0]
        if not pool:
            break
        picked = take_one(
            pool,
            lambda u: (
                -_theme_bonus(u, theme),
                abs(u["pts"] - heavy_ideal),
            ),
        )
        if not picked:
            break
        heavies_taken += 1

    support_target = 1 if budget < 1500 else 2
    support_ideal = budget * 0.08
    support_taken = 0
    while support_taken < support_target:
        pool = [u for u in support if counts.get(u["name"], 0) == 0]
        if not pool:
            break
        picked = take_one(
            pool,
            lambda u: (
                -_theme_bonus(u, theme),
                abs(u["pts"] - support_ideal),
            ),
        )
        if not picked:
            break
        support_taken += 1

    min_useful = max(40, cheapest)
    progressed = True
    while remaining >= min_useful and progressed:
        progressed = False
        for u in bl_pool:
            if can_take(u):
                take(u)
                progressed = True
                break
        if progressed:
            continue
        fill_pool = sorted(
            [u for u in all_units if u["pts"] <= remaining],
            key=lambda u: (-_theme_bonus(u, theme), u["pts"]),
        )
        for u in fill_pool:
            if can_take(u):
                take(u)
                progressed = True
                break

    if not picks:
        return None

    ordered_names: list[str] = []
    pts_by_name: dict[str, int] = {}
    for p in picks:
        if p["name"] not in pts_by_name:
            ordered_names.append(p["name"])
            pts_by_name[p["name"]] = p["pts"]

    total = sum(p["pts"] for p in picks)
    lines: list[str] = []
    for name in ordered_names:
        n = counts[name]
        per = pts_by_name[name]
        suffix = f" (x{n})" if n > 1 else ""
        lines.append(f"- {name}{suffix}: {per * n} pts")
    lines.append(f"Total: {total}/{budget} points")

    header_bits = [f"{faction_name or 'Army'} — {budget} pts"]
    if theme:
        header_bits.append(f"theme: {theme}")
    header = " | ".join(header_bits)
    return f"{header}\n" + "\n".join(lines)



def load_index(index_dir: str) -> FAISS:
    """Load a FAISS index from disk."""
    if not os.path.isdir(index_dir):
        raise SystemExit(
            f"FAISS index not found at '{index_dir}'. "
            "Build it first with: python build_index.py --game <game>"
        )
    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    return FAISS.load_local(index_dir, embeddings, allow_dangerous_deserialization=True)



def load_rules_sources(data_dir: str) -> List[Tuple[str, str]]:
    """Return all markdown files as (path, text) pairs for keyword lookups."""
    sources: List[Tuple[str, str]] = []
    if not os.path.isdir(data_dir):
        return sources
    for name in sorted(os.listdir(data_dir)):
        if not name.lower().endswith(".md"):
            continue
        path = os.path.join(data_dir, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                sources.append((path, f.read()))
        except OSError:
            continue
    return sources



def retrieve_context(vectorstore: FAISS, question: str, k: int = 10) -> List[str]:
    """
    Retrieve the top-k most relevant chunks using Max Marginal Relevance.
    MMR balances relevance and diversity, which helps when the same information
    appears in multiple files (e.g. core rules vs. faction supplements).
    """
    docs = vectorstore.max_marginal_relevance_search(
        question,
        k=k,
        fetch_k=max(30, k * 6),
        lambda_mult=0.5,
    )

    snippets: List[str] = []
    for doc in docs:
        meta = doc.metadata or {}
        label_parts: List[str] = []
        if meta.get("doc_kind"):
            label_parts.append(str(meta["doc_kind"]))
        if meta.get("faction"):
            label_parts.append(str(meta["faction"]))
        for heading_key in ("h3", "h2", "h1"):
            if meta.get(heading_key):
                label_parts.append(str(meta[heading_key]))
                break

        label = " | ".join(label_parts)
        snippets.append(f"[{label}]\n{doc.page_content}" if label else doc.page_content)

    return snippets



_STOPWORDS = {
    "a", "an", "and", "the", "of", "for", "to", "in", "on", "with",
    "without", "unit", "units", "model", "models", "squad", "team",
    "detachment",
}


def _normalize(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokenize(text: str) -> List[str]:
    return [t for t in _normalize(text).split() if t and t not in _STOPWORDS]


def _overlap(a: Sequence[str], b: Sequence[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)



def build_heading_vocabulary(sources: Sequence[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """
    Extract all H2–H4 heading names from the loaded markdown sources.
    Returns a list of (normalized, original) pairs used for spell correction.
    Calling this once at startup and caching the result avoids per-request work.
    """
    vocab: List[Tuple[str, str]] = []
    seen: set = set()
    for _path, text in sources:
        for m in re.finditer(r"^#{2,4}\s+(.+?)\s*$", text, re.MULTILINE):
            heading = m.group(1).strip()
            norm = _normalize(heading)
            if norm and norm not in seen:
                seen.add(norm)
                vocab.append((norm, heading))
    return vocab


def spell_correct_phrase(
    phrase: str,
    vocab: List[Tuple[str, str]],
    threshold: float = 0.74,
) -> str:
    """
    Return the closest vocabulary heading if it is a strong fuzzy match for
    `phrase`, otherwise return `phrase` unchanged.

    The threshold is set at 0.74 — high enough to avoid false corrections of
    correctly-spelled phrases, low enough to catch common single-character typos
    ("cranlats" → "Clanrats", str_sim ≈ 0.75; "Dtormvermin" → "Stormvermin",
    str_sim ≈ 0.91). The extra guard `_normalize(best_original) != phrase_norm`
    ensures exact matches are always returned unchanged.
    """
    if not vocab or not phrase:
        return phrase

    phrase_norm = _normalize(phrase)
    phrase_toks = _tokenize(phrase)

    best_score = 0.0
    best_original = phrase

    for norm, original in vocab:
        str_sim = difflib.SequenceMatcher(None, phrase_norm, norm).ratio()
        if str_sim <= best_score:
            continue
        tok_sim = _overlap(phrase_toks, _tokenize(original))
        score = max(str_sim, tok_sim)
        if score > best_score:
            best_score = score
            best_original = original

    if best_score >= threshold and _normalize(best_original) != phrase_norm:
        return best_original
    return phrase



def detect_faction_query(
    question: str,
    sources: Sequence[Tuple[str, str]],
) -> Optional[Tuple[str, str]]:
    """
    Detect when a question asks a faction-wide comparative or recommendation
    question (e.g. "What is the best Skaven unit?", "List all Space Marines").

    Returns (faction_name, faction_file_text) when both conditions are met:
      1. The question contains a comparative/superlative signal word.
      2. A source file whose name token-overlaps with the question is found
         AND that file contains a ## Units section (i.e. it is a faction file,
         not a core-rules or supplement file).

    Returns None otherwise.
    """
    return detect_faction_source(
        question,
        sources,
        require_units=True,
        signals=_FACTION_COMPARATIVE_SIGNALS,
    )


def build_unit_summary(faction_text: str, faction_name: str) -> str:
    """
    Build a compact one-line-per-unit overview of a faction's units.

    Each line contains the unit name and its full stat line
    (e.g. "**Points:** 110 | **Move:** 4\" | **Health:** 1 | …").
    Only H3 headings followed by a **Points:** line within the next 400
    characters are included, which naturally excludes ability/rule sub-sections
    that don't have stats.

    The resulting block is small enough (~30–50 lines) to prepend to the AI's
    context without significantly increasing token usage, while giving it
    everything needed to compare all units in the faction.
    """
    lines: List[str] = []

    for unit_m in re.finditer(r"^### (.+?)\s*$", faction_text, re.MULTILINE):
        unit_name = unit_m.group(1).strip()
        chunk = faction_text[unit_m.start(): unit_m.start() + 400]
        points_m = re.search(r"\*\*Points:\*\*[^\n]+", chunk)
        if points_m:
            lines.append(f"- **{unit_name}**: {points_m.group(0)}")

    if not lines:
        return ""

    return (
        f"[{faction_name} | all units with stats — use for faction-wide comparisons]\n"
        + "\n".join(lines)
    )


def build_points_table_summary(faction_text: str, faction_name: str) -> str:
    match = re.search(
        r"^## Points Table\s*$([\s\S]+?)(?=^##\s+|\Z)",
        faction_text,
        re.MULTILINE,
    )
    if not match:
        return ""

    section = match.group(0).strip()
    return f"[{faction_name} | full faction points table]\n{section}"


_FILTER_WORDS = {
    "which", "what", "who", "where", "when", "how", "why",
    "more", "less", "better", "worse", "many", "much",
}

_COMPARISON_SIGNALS = {
    "compare", "comparing", "compared", "comparison",
    "difference", "differences", "different",
    "same", "similar", "both", "common",
}

_GAME_PROPERTY_WORDS = {
    "point", "points", "pts",
    "save", "wound", "wounds", "health",
    "attack", "attacks", "move", "movement",
    "control", "toughness", "keyword", "keywords",
    "ability", "abilities", "trait", "traits", "passive", "passives",
    "definition", "defenition", "text", "effect",
    "stat", "stats",
    "profile", "warscroll", "datasheet", "rule", "rules",
}

_GAME_PROPERTY_STOP = _FILTER_WORDS | _GAME_PROPERTY_WORDS | {
    "unit", "units", "model", "models", "squad", "team",
    "does", "have", "has", "give", "gives", "provide", "provides",
    "cost", "costs", "this", "that", "their", "there",
    "also", "with", "from", "just", "only", "each", "every",
    "will", "cant", "can", "its", "the", "are", "for",
}

_FACTION_COMPARATIVE_SIGNALS = frozenset({
    "best", "worst", "strongest", "weakest", "toughest", "fastest",
    "cheapest", "most expensive", "most powerful", "most versatile",
    "recommend", "recommended", "top pick", "top unit",
    "most attacks", "most damage", "most health", "most wounds",
    "highest points", "lowest points", "fewest points",
    "all units", "compare all", "list all", "overview",
})

_FACTION_POINTS_SIGNALS = frozenset({
    "1000 point", "1000 points", "2000 point", "2000 points",
    "army", "army list", "list", "roster", "build", "building",
    "good", "best", "recommend", "recommended",
    "point", "points", "pts", "cheap", "cheapest",
    "expensive", "cost", "costs",
    "all units", "list all", "overview",
})

_ARMY_LIST_STRONG_PHRASES = frozenset({
    "army list", "army build", "army composition", "army roster",
    "starter army", "starter force", "starter list",
    "list building", "list-building",
})

_ARMY_LIST_VERB_PATTERN = re.compile(
    r"\b(?:build|make|create|design|recommend|suggest|write|give|draft|put\s+together)"
    r"(?:\s+(?:me|us|a|an|the))*"
    r"(?:\s+\w+){0,6}?"
    r"\s+(?:army|list|roster|force)\b",
    re.IGNORECASE,
)

_ARMY_LIST_WEAK_SIGNALS = frozenset({
    "army", "list", "roster", "build", "building", "good",
    "recommend", "recommended", "suggest", "force",
})

_DEFAULT_ARMY_BUDGET = 2000


def _detect_army_query(question: str) -> tuple[bool, Optional[int]]:
    """
    Return (is_army_query, budget). Order of precedence:
      1. Fixed strong phrase or verb-pattern match -> army mode, budget from
         text or default.
      2. Budget present + weak signal -> army mode, explicit budget.
      3. Otherwise -> rule mode.
    """
    q = question.lower()
    budget = _extract_points_budget(question)

    strong = (
        any(phrase in q for phrase in _ARMY_LIST_STRONG_PHRASES)
        or bool(_ARMY_LIST_VERB_PATTERN.search(question))
    )
    weak = any(sig in q for sig in _ARMY_LIST_WEAK_SIGNALS)

    if strong:
        return True, budget or _DEFAULT_ARMY_BUDGET
    if budget and weak:
        return True, budget
    return False, None


_CORE_CONCEPTS_40K: list[tuple[frozenset[str], tuple[str, ...]]] = [
    (
        frozenset({
            "same time", "simultaneous", "simultaneously", "sequenc",
            "resolve first", "resolve order", "order of resolution",
            "which resolves first", "who resolves first",
            "resolve before", "resolves before", "resolved before",
            "resolve after", "resolves after", "resolved after",
            "take effect", "takes effect",
        }),
        ("SEQUENCING",),
    ),
    (
        frozenset({
            "fight first", "fights first", "strike first", "strike-first",
            "fight order", "who fights first", "fight immediately",
            "fight before", "interrupt", "pre-empt", "preempt",
        }),
        ("FIGHT PHASE", "FIGHTS FIRST"),
    ),
    (
        frozenset({
            "charge phase", "finish a charge", "finishes a charge",
            "ends a charge", "charge ends", "end of charge",
            "when a charge", "after charging", "after a charge",
            "charge move", "when a unit charges", "declare a charge",
        }),
        ("CHARGE PHASE", "CHARGING WITH A UNIT"),
    ),
    (
        frozenset({"fight phase", "combat phase", "melee phase"}),
        ("FIGHT PHASE",),
    ),
    (
        frozenset({"command phase"}),
        ("COMMAND PHASE",),
    ),
    (
        frozenset({"movement phase", "normal move", "advance"}),
        ("MOVEMENT PHASE",),
    ),
    (
        frozenset({"shooting phase", "shoot", "ranged attack"}),
        ("SHOOTING PHASE",),
    ),
    (
        frozenset({"battle round", "turn order", "turn sequence"}),
        ("THE BATTLE ROUND",),
    ),
]

_CORE_CONCEPTS_AOS: list[tuple[frozenset[str], tuple[str, ...]]] = [
    (
        frozenset({
            "strike first", "strike-first", "strike last", "strike-last",
            "fight first", "fights first", "fight order",
            "who fights first", "fight immediately", "interrupt",
        }),
        ("STRIKE-FIRST AND STRIKE-LAST", "FIGHT ABILITIES", "COMBAT PHASE"),
    ),
    (
        frozenset({
            "same time", "simultaneous", "simultaneously",
            "resolve first", "resolve order", "battle sequence",
            "resolve before", "resolves before", "resolved before",
            "resolve after", "resolves after", "resolved after",
            "take effect", "takes effect",
        }),
        ("BATTLE SEQUENCE",),
    ),
    (
        frozenset({
            "charge phase", "finish a charge", "finishes a charge",
            "ends a charge", "charge ends", "end of charge",
            "when a charge", "after charging", "after a charge",
            "counter-charge", "counter charge", "when a unit charges",
        }),
        ("CHARGE PHASE", "CHARGE PHASE COMMANDS"),
    ),
    (
        frozenset({"combat phase", "fight phase", "melee phase"}),
        ("COMBAT PHASE", "FIGHT ABILITIES"),
    ),
    (
        frozenset({"hero phase"}),
        ("HERO PHASE COMMANDS",),
    ),
    (
        frozenset({"movement phase", "normal move", "run", "retreat"}),
        ("MOVEMENT PHASE",),
    ),
    (
        frozenset({"shooting phase", "shoot", "ranged attack"}),
        ("SHOOTING PHASE", "SHOOTING PHASE COMMANDS"),
    ),
    (
        frozenset({"turn phases", "turn order", "turn sequence", "battle round"}),
        ("TURN PHASES", "BATTLE SEQUENCE"),
    ),
    (
        frozenset({
            "trigger", "triggered", "reactive", "reaction",
            "enemy phase", "any phase", "when an enemy",
            "ability timing", "timing", "once per",
        }),
        ("ADVANCED ABILITY RULES", "'ONCE PER' TIMINGS"),
    ),
]


def _is_core_rules_file(path: str) -> bool:
    stem = os.path.splitext(os.path.basename(path))[0].lower()
    return "core" in stem and "rule" in stem


def _find_heading_section(text: str, heading_name: str) -> Optional[str]:
    """Locate an H2/H3/H4 heading whose name matches `heading_name` (case- and
    numbering-insensitive) and return its full section."""
    target_norm = _normalize(heading_name)
    if not target_norm:
        return None
    for m in re.finditer(r"^(#{2,4})\s+(.+?)\s*$", text, re.MULTILINE):
        level = len(m.group(1))
        heading = m.group(2).strip()
        heading_bare = re.sub(r"^[\d.\s]+", "", heading)
        if _normalize(heading_bare) == target_norm:
            section = _extract_markdown_section(text, m.start(), level)
            if section:
                return section
    return None


def retrieve_concept_sections(
    question: str,
    sources: Sequence[Tuple[str, str]],
    game: str,
    max_sections: int = 4,
) -> List[str]:
    """
    Return canonical core-rule sections whose concepts are referenced by the
    question (e.g. sequencing, fight order, charge phase triggers).

    Unlike the unit/ability keyword search, this targets *rules-terminology*
    in the question and pulls the authoritative core-rules heading so the model
    always has the governing framework for multi-rule timing questions.
    """
    q_lower = question.lower()
    concepts = _CORE_CONCEPTS_40K if game == "wh40k" else _CORE_CONCEPTS_AOS

    wanted: list[str] = []
    seen: set[str] = set()
    for triggers, headings in concepts:
        if not any(trig in q_lower for trig in triggers):
            continue
        for heading in headings:
            key = heading.lower()
            if key not in seen:
                seen.add(key)
                wanted.append(heading)

    if not wanted:
        return []

    core_sources = [(p, t) for p, t in sources if _is_core_rules_file(p)]
    if not core_sources:
        return []

    out: list[str] = []
    for heading in wanted:
        if len(out) >= max_sections:
            break
        for path, text in core_sources:
            section = _find_heading_section(text, heading)
            if section:
                label = f"[{os.path.basename(path)} | {heading}]"
                out.append(f"{label}\n{section}")
                break

    return out


def extract_candidate_phrases(question: str) -> List[str]:
    """
    Extract proper-noun-like phrases from the question that likely refer to
    specific units, abilities, or keywords in the rules.
    """
    phrases: List[str] = []
    q_lower = question.lower()

    for m in re.finditer(r'["\u201c\u2018]([^"\u201d\u2019]{3,80})["\u201d\u2019]', question):
        phrases.append(m.group(1).strip())

    for m in re.finditer(
        r"\b(?:definition|defenition|meaning|effect|text)\s+of\s+(?:the\s+)?"
        r"([A-Za-z][A-Za-z'\-]+(?:\s+[A-Za-z][A-Za-z'\-]+){0,5})\s+"
        r"(?:trait|ability|rule|keyword|passive|passive trait|special rule)\b",
        question,
        re.IGNORECASE,
    ):
        phrases.append(m.group(1).strip())

    for m in re.finditer(
        r"\bwhat\s+does\s+([A-Za-z][A-Za-z'\-]+(?:\s+[A-Za-z][A-Za-z'\-]+){0,5})\s+"
        r"(?:trait|ability|rule|keyword|passive)\s+do\b",
        question,
        re.IGNORECASE,
    ):
        phrases.append(m.group(1).strip())

    if any(kw in q_lower for kw in ("point", "points", "pts")):
        for pattern in (
            r"\bunit\s+([A-Za-z][A-Za-z'\-]+(?:\s+[A-Za-z][A-Za-z'\-]+){0,4})",
            r"\bpoints?\b[^A-Za-z0-9]{0,10}(?:is|are|for)\s+([A-Za-z][A-Za-z'\-]+(?:\s+[A-Za-z][A-Za-z'\-]+){0,4})",
        ):
            for m in re.finditer(pattern, question, re.IGNORECASE):
                phrases.append(m.group(1).strip())

    for m in re.finditer(
        r"([A-Z][A-Za-z]+(?:-[A-Za-z]+)*(?: [A-Z][A-Za-z]+(?:-[A-Za-z]+)*)+)",
        question,
    ):
        phrases.append(m.group(1).strip())

    for m in re.finditer(r"\b([A-Z][A-Za-z]{3,})\b", question):
        phrases.append(m.group(1).strip())

    for m in re.finditer(r"\b([A-Z][A-Za-z]{1,}(?:-[A-Za-z]{2,})+)\b", question):
        phrases.append(m.group(1).strip())

    if "unit " in q_lower:
        for m in re.finditer(
            r"\bunit\s+([a-z][a-z'\-]{3,}(?:\s+[a-z][a-z'\-]{3,}){0,4})\b",
            question,
            re.IGNORECASE,
        ):
            phrases.append(m.group(1).strip())

    for m in re.finditer(
        r"\b([A-Za-z][A-Za-z'\-]{2,}(?:\s+[A-Za-z][A-Za-z'\-]{2,}){0,2})"
        r"\s+(?:or|vs\.?|versus)\s+"
        r"([A-Za-z][A-Za-z'\-]{2,}(?:\s+[A-Za-z][A-Za-z'\-]{2,}){0,2})\b",
        question,
        re.IGNORECASE,
    ):
        for grp in (m.group(1).strip(), m.group(2).strip()):
            if _normalize(grp) not in _FILTER_WORDS:
                phrases.append(grp)

    for m in re.finditer(
        r"\bbetween\s+([A-Za-z][A-Za-z'\-]{2,}(?:\s+[A-Za-z][A-Za-z'\-]{2,}){0,2}?)"
        r"\s+and\s+"
        r"([A-Za-z][A-Za-z'\-]{2,}(?:\s+[A-Za-z][A-Za-z'\-]{2,}){0,2}?)\b",
        question,
        re.IGNORECASE,
    ):
        for grp in (m.group(1).strip(), m.group(2).strip()):
            if _normalize(grp) not in _FILTER_WORDS:
                phrases.append(grp)

    if any(sig in q_lower for sig in _COMPARISON_SIGNALS):
        for m in re.finditer(
            r"\b([A-Za-z][A-Za-z'\-]{3,})\s+and\s+([A-Za-z][A-Za-z'\-]{3,})\b",
            question,
            re.IGNORECASE,
        ):
            for grp in (m.group(1).strip(), m.group(2).strip()):
                if _normalize(grp) not in _FILTER_WORDS:
                    phrases.append(grp)

    if any(kw in q_lower for kw in _GAME_PROPERTY_WORDS):
        for m in re.finditer(r"\b([a-z][a-z'\-]{3,})\b", question):
            candidate = m.group(1).strip()
            norm = _normalize(candidate)
            if norm not in _GAME_PROPERTY_STOP and not any(
                norm == _normalize(p) for p in phrases
            ):
                phrases.append(candidate)

    seen: set = set()
    result: List[str] = []
    for p in phrases:
        key = _normalize(p)
        if len(p) >= 4 and key not in seen:
            seen.add(key)
            result.append(p)

    return result


def _has_any_signal(question: str, signals: Sequence[str]) -> bool:
    q_lower = question.lower()
    for sig in signals:
        words = sig.split()
        if all(word in q_lower for word in words):
            return True
    return False


def detect_faction_source(
    question: str,
    sources: Sequence[Tuple[str, str]],
    *,
    require_units: bool = True,
    signals: Sequence[str] | None = None,
) -> Optional[Tuple[str, str]]:
    if signals and not _has_any_signal(question, signals):
        return None

    q_toks = set(_tokenize(question))
    best_match: Optional[Tuple[str, str]] = None
    best_score = 0.0

    for path, text in sources:
        if require_units and "## Units" not in text:
            continue

        faction_name = os.path.splitext(os.path.basename(path))[0]
        faction_toks = [t for t in _tokenize(faction_name) if len(t) > 3]
        if not faction_toks:
            continue

        overlap = len(set(faction_toks) & q_toks) / len(faction_toks)
        if overlap > best_score:
            best_score = overlap
            best_match = (faction_name, text)

    return best_match if best_score > 0 else None


def _extract_markdown_section(text: str, start: int, level: int) -> str:
    """Return the markdown section starting at `start` until the next heading of same/higher level."""
    for m in re.finditer(r"^(#{1,6})\s+.+$", text, re.MULTILINE):
        if m.start() <= start:
            continue
        if len(m.group(1)) <= level:
            return text[start : m.start()].strip()
    return text[start:].strip()


def _heading_keyword_search(
    sources: Sequence[Tuple[str, str]],
    phrase: str,
    prefer_points: bool,
    max_results: int,
) -> List[str]:
    """
    Find markdown headings that match `phrase` and return their full sections.
    Scores matches by exactness, token overlap, and string similarity.
    """
    needle_norm = _normalize(phrase)
    needle_toks = _tokenize(phrase)
    if not needle_norm:
        return []

    results: List[Tuple[int, str]] = []

    for path, text in sources:
        file_stem = os.path.splitext(os.path.basename(path))[0]
        file_toks = set(_tokenize(file_stem))

        for m in re.finditer(r"^(#{2,4})\s+(.+?)\s*$", text, re.MULTILINE):
            level = len(m.group(1))
            heading = m.group(2).strip()
            heading_norm = _normalize(heading)
            heading_toks = _tokenize(heading)

            exact = heading_norm == needle_norm and bool(heading_norm)
            tok_sim = _overlap(needle_toks, heading_toks)
            str_sim = (
                difflib.SequenceMatcher(None, needle_norm, heading_norm).ratio()
                if needle_norm and heading_norm
                else 0.0
            )

            if not exact and tok_sim < 0.45 and str_sim < 0.72:
                continue

            section = _extract_markdown_section(text, m.start(), level)
            if not section:
                continue

            score = 0
            if exact:
                score += 25
            score += int(tok_sim * 20)
            score += int(str_sim * 10)
            if prefer_points and "**points:**" in section.lower():
                score += 12
            if file_toks and needle_toks:
                score += min(8, len(set(needle_toks) & file_toks) * 3)

            results.append((score, f"[{os.path.basename(path)} | heading]\n{section}"))

    results.sort(key=lambda t: t[0], reverse=True)
    return [s for _, s in results[:max_results]]


def _window_keyword_search(
    sources: Sequence[Tuple[str, str]],
    phrase: str,
    prefer_points: bool,
    window: int,
    max_results: int,
) -> List[str]:
    """
    Fallback: find literal occurrences of `phrase` and return surrounding text windows.
    """
    phrase_clean = phrase.strip().strip(string.punctuation)
    if len(phrase_clean) < 3:
        return []

    results: List[Tuple[int, str]] = []

    for path, text in sources:
        for m in re.finditer(re.escape(phrase_clean), text, re.IGNORECASE):
            idx = m.start()
            start = max(0, idx - window // 2)
            end = min(len(text), idx + len(phrase_clean) + window // 2)
            snippet = text[start:end].strip()
            if not snippet:
                continue

            s_lower = snippet.lower()
            score = 0
            if prefer_points and "**points:**" in s_lower:
                score += 8
            if re.search(rf"^###\s+{re.escape(phrase_clean)}\s*$", snippet, re.IGNORECASE | re.MULTILINE):
                score += 12
            if re.search(rf"^##\s+{re.escape(phrase_clean)}\s*$", snippet, re.IGNORECASE | re.MULTILINE):
                score += 6

            results.append((score, f"[{os.path.basename(path)} | match]\n{snippet}"))

    results.sort(key=lambda t: t[0], reverse=True)
    return [s for _, s in results[:max_results]]


def find_keyword_snippets(
    sources: Sequence[Tuple[str, str]],
    question: str,
    phrases: List[str],
    max_snippets: int = 3,
    window: int = 600,
    heading_vocab: List[Tuple[str, str]] | None = None,
) -> List[str]:
    """
    For each extracted candidate phrase, try a structure-aware heading match first,
    then fall back to a sliding-window keyword match.

    If `heading_vocab` is supplied (a list of (normalized, original) tuples built
    from the loaded sources), each phrase is spell-corrected against the vocabulary
    before searching. This allows queries with minor typos (e.g. "cranlats" →
    "Clanrats") to resolve correctly even in the window search, which uses exact
    string matching.
    """
    q_lower = question.lower()
    prefer_points = any(kw in q_lower for kw in ("point", "points", "pts"))

    out: List[str] = []
    for phrase in phrases:
        if len(out) >= max_snippets:
            break

        corrected = spell_correct_phrase(phrase, heading_vocab or [])

        sections = _heading_keyword_search(sources, corrected, prefer_points=prefer_points, max_results=1)
        if sections:
            out.extend(sections)
            continue

        windows = _window_keyword_search(
            sources, corrected, prefer_points=prefer_points, window=window, max_results=1
        )
        out.extend(windows)

    return out[:max_snippets]



def answer_question(
    question: str,
    vectorstore: FAISS,
    game_label: str,
    data_dir: str | None = None,
    model_name: str = DEFAULT_CHAT_MODEL,
    system_prompt: str = SYSTEM_PROMPT,
    k: int = 10,
    rules_sources: Sequence[Tuple[str, str]] | None = None,
    heading_vocab: List[Tuple[str, str]] | None = None,
) -> str:
    """
    Retrieve relevant rules context and ask the chat model to answer the question.

    Args:
        question:      The user's rules question.
        vectorstore:   Pre-loaded FAISS index for the target game.
        game_label:    Human-readable game name ("Warhammer Age of Sigmar", etc.)
        data_dir:      Path to the markdown files (enables keyword search). Optional.
        model_name:    OpenAI chat model identifier.
        system_prompt: Instructions for the model.
        k:             Number of semantic chunks to retrieve.
        heading_vocab: Pre-built heading vocabulary for spell correction. Build once
                       at startup with build_heading_vocabulary(sources) and pass here
                       to avoid per-request overhead.

    Returns:
        The model's answer as a string.
    """
    game_key = "wh40k" if "40" in game_label else "aos"

    phrases = extract_candidate_phrases(question)
    is_conceptual = not phrases or all(len(p.split()) == 1 for p in phrases)
    effective_k = max(k, 14) if is_conceptual else k

    context_snippets = retrieve_context(vectorstore, question, k=effective_k)

    keyword_snippets: List[str] = []
    sources = rules_sources

    if sources is None and data_dir and phrases:
        sources = load_rules_sources(data_dir)

    if sources and phrases:
        max_kw = min(6, max(3, len(phrases)))
        keyword_snippets = find_keyword_snippets(
            sources, question, phrases,
            max_snippets=max_kw,
            heading_vocab=heading_vocab,
        )

    concept_snippets: List[str] = []
    if sources is None and data_dir:
        sources = load_rules_sources(data_dir)
    if sources:
        concept_snippets = retrieve_concept_sections(
            question, sources, game=game_key, max_sections=4,
        )

    faction_summary: Optional[str] = None
    if sources:
        faction_data = detect_faction_query(question, sources)
        if faction_data:
            faction_name, faction_text = faction_data
            summary = build_unit_summary(faction_text, faction_name)
            if summary:
                faction_summary = summary
                context_snippets = context_snippets[:5]

    points_table_summary: Optional[str] = None
    if sources:
        faction_points_data = detect_faction_source(
            question,
            sources,
            require_units=True,
            signals=_FACTION_POINTS_SIGNALS,
        )
        if faction_points_data:
            faction_name, faction_text = faction_points_data
            summary = build_points_table_summary(faction_text, faction_name)
            if summary:
                points_table_summary = summary
                context_snippets = context_snippets[:4]

    prefer_points = any(kw in question.lower() for kw in ("point", "points", "pts"))
    if prefer_points and keyword_snippets:
        points_found = sum(1 for s in keyword_snippets if "**Points:**" in s)
        num_subjects = len(phrases) if phrases else 1
        if points_found >= num_subjects:
            context_snippets = context_snippets[:3]
        elif points_found > 0:
            context_snippets = context_snippets[:6]

    prefix: List[str] = []
    if points_table_summary:
        prefix.append(points_table_summary)
    if faction_summary:
        prefix.append(faction_summary)
    all_snippets = prefix + keyword_snippets + concept_snippets + context_snippets
    context_block = "\n\n---\n\n".join(all_snippets)

    llm = ChatOpenAI(model=model_name, temperature=0.2)

    army_list_query, budget = _detect_army_query(question)

    if army_list_query and budget and points_table_summary:
        precomputed = None
        faction_pts_data = detect_faction_source(
            question, sources or [],
            require_units=True, signals=_FACTION_POINTS_SIGNALS,
        )
        if faction_pts_data:
            precomputed = _build_army_list_from_table(
                faction_pts_data[1], budget, game=game_key, question=question,
            )

        hint = ""
        if precomputed:
            hint = (
                f"\n\nA balanced, thematic army list fitting {budget} points has "
                f"been pre-computed for you. It already respects the budget, "
                f"reinforces core battleline, includes a centerpiece, and biases "
                f"toward a single sub-faction for cohesion.\n\n"
                f"{precomputed}\n\n"
                f"STRICT: use this list as-is. Do NOT add, remove, or swap units. "
                f"Do NOT recalculate — just copy the bullet list and total into "
                f"your answer verbatim. Your 2-3 explanatory sentences should "
                f"describe why this composition works (centerpiece, core, "
                f"support roles, shared sub-faction keyword if present)."
            )

        messages = [
            (
                "system",
                f"{ARMY_LIST_SYSTEM_PROMPT}\n\nYou are building an army for: {game_label}.",
            ),
            (
                "system",
                f"Rules context:\n\n{context_block}{hint}",
            ),
            ("user", question),
        ]
    else:
        messages = [
            (
                "system",
                f"{system_prompt}\n\nYou are answering rules questions for: {game_label}.",
            ),
            (
                "system",
                "Below is the relevant rules context retrieved from the selected game's "
                "rules files. When a faction points table is present, you may use it to "
                "reason about army construction, unit costs, and broad faction overviews. "
                "Answer ONLY using information that appears here.\n\n"
                f"{context_block}",
            ),
            ("user", question),
        ]

    response = llm.invoke(messages)
    return response.content.strip()



def main() -> int:
    load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))

    parser = argparse.ArgumentParser(
        description="Ask Warhammer rules questions using RAG + OpenAI."
    )
    parser.add_argument(
        "--game",
        choices=["aos", "wh40k"],
        required=True,
        help="Which game system to query: 'aos' or 'wh40k'.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_CHAT_MODEL,
        help=f"OpenAI chat model to use (default: {DEFAULT_CHAT_MODEL}).",
    )
    parser.add_argument(
        "--index-dir",
        help="Override the FAISS index directory.",
    )
    parser.add_argument(
        "--data-dir",
        help="Override the markdown source directory (used for keyword search).",
    )
    parser.add_argument(
        "question",
        nargs="?",
        help="Question to answer. If omitted, an interactive REPL is started.",
    )

    args = parser.parse_args()

    if args.game == "aos":
        index_dir = args.index_dir or DEFAULT_AOS_INDEX_DIR
        data_dir = args.data_dir or DEFAULT_AOS_DATA_DIR
        game_label = "Warhammer Age of Sigmar"
    else:
        index_dir = args.index_dir or DEFAULT_WH40K_INDEX_DIR
        data_dir = args.data_dir or DEFAULT_WH40K_DATA_DIR
        game_label = "Warhammer 40,000"

    print(f"Loading index from: {index_dir}")
    vectorstore = load_index(index_dir)

    def ask(question: str) -> str:
        return answer_question(
            question=question,
            vectorstore=vectorstore,
            game_label=game_label,
            data_dir=data_dir,
            model_name=args.model,
        )

    if args.question:
        print(f"\n=== {game_label} Rules Q&A ===\n")
        print(ask(args.question))
        return 0

    print(f"\n{game_label} Rules Q&A — type 'exit' or press Ctrl+C to quit.\n")
    while True:
        try:
            user_input = input("Your question> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            print("Goodbye.")
            break

        print("\n--- Answer ---\n")
        print(ask(user_input))
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
