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
from typing import List, Sequence, Tuple

from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

# Paths are relative to this script's location (python/)
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
- If the answer depends on definitions, sequences, or edge cases, walk through them step by step.
- If the context does NOT contain enough information to answer with confidence, say you are unsure
  and clearly state what is missing rather than inventing rules.
- Do NOT reference page numbers unless they are explicitly present in the provided context.
- Be concise, but do not omit important conditions or exceptions.

When the user names a specific unit, ability, or keyword:
- Prioritise any context snippets that mention that exact name (case-insensitive).
- Pay particular attention to short "notes" sentences such as "This unit cannot be reinforced."
- If such a sentence is present in the context, treat it as authoritative for the question.

Assume the user is familiar with basic tabletop gaming, but not necessarily all Warhammer jargon.
Explain specialised terms briefly when they are important to the answer.

Always structure your final answer in exactly this format:

**Short Answer:** <one-line answer>

**Detailed Answer:** <longer explanation with relevant conditions, edge cases, and quotations>

**Source:** <brief description of where this comes from in the provided context>
""".strip()


# ---------------------------------------------------------------------------
# Index loading
# ---------------------------------------------------------------------------

def load_index(index_dir: str) -> FAISS:
    """Load a FAISS index from disk."""
    if not os.path.isdir(index_dir):
        raise SystemExit(
            f"FAISS index not found at '{index_dir}'. "
            "Build it first with: python build_index.py --game <game>"
        )
    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    return FAISS.load_local(index_dir, embeddings, allow_dangerous_deserialization=True)


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Semantic retrieval
# ---------------------------------------------------------------------------

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
        # Include the most specific heading available for orientation.
        for heading_key in ("h3", "h2", "h1"):
            if meta.get(heading_key):
                label_parts.append(str(meta[heading_key]))
                break

        label = " | ".join(label_parts)
        snippets.append(f"[{label}]\n{doc.page_content}" if label else doc.page_content)

    return snippets


# ---------------------------------------------------------------------------
# Keyword / structure-aware retrieval
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Heading vocabulary & spell correction
# ---------------------------------------------------------------------------

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
    "ability", "abilities", "stat", "stats",
    "profile", "warscroll", "datasheet", "rule", "rules",
}

_GAME_PROPERTY_STOP = _FILTER_WORDS | _GAME_PROPERTY_WORDS | {
    "unit", "units", "model", "models", "squad", "team",
    "does", "have", "has", "give", "gives", "provide", "provides",
    "cost", "costs", "this", "that", "their", "there",
    "also", "with", "from", "just", "only", "each", "every",
    "will", "cant", "can", "its", "the", "are", "for",
}


def extract_candidate_phrases(question: str) -> List[str]:
    """
    Extract proper-noun-like phrases from the question that likely refer to
    specific units, abilities, or keywords in the rules.
    """
    phrases: List[str] = []
    q_lower = question.lower()

    # Anything the user explicitly quotes (ability / unit names).
    for m in re.finditer(r'["\u201c\u2018]([^"\u201d\u2019]{3,80})["\u201d\u2019]', question):
        phrases.append(m.group(1).strip())

    # Points queries: capture the noun after "unit <name>" or "points for/is <name>".
    if any(kw in q_lower for kw in ("point", "points", "pts")):
        for pattern in (
            r"\bunit\s+([A-Za-z][A-Za-z'\-]+(?:\s+[A-Za-z][A-Za-z'\-]+){0,4})",
            r"\bpoints?\b[^A-Za-z0-9]{0,10}(?:is|are|for)\s+([A-Za-z][A-Za-z'\-]+(?:\s+[A-Za-z][A-Za-z'\-]+){0,4})",
        ):
            for m in re.finditer(pattern, question, re.IGNORECASE):
                phrases.append(m.group(1).strip())

    # Two or more consecutive Title-Case words, including hyphenated tokens
    # (e.g. "Chaos Warriors", "Lord-Aquilor on Gryph-charger").
    for m in re.finditer(
        r"([A-Z][A-Za-z]+(?:-[A-Za-z]+)*(?: [A-Z][A-Za-z]+(?:-[A-Za-z]+)*)+)",
        question,
    ):
        phrases.append(m.group(1).strip())

    # Single long Title-Case token (e.g. "Stormvermin", "DeepStrike").
    for m in re.finditer(r"\b([A-Z][A-Za-z]{3,})\b", question):
        phrases.append(m.group(1).strip())

    # Hyphenated Title-Case names not captured above (e.g. "Lord-Aquilor").
    for m in re.finditer(r"\b([A-Z][A-Za-z]{1,}(?:-[A-Za-z]{2,})+)\b", question):
        phrases.append(m.group(1).strip())

    # Lowercase "unit <name>" fallback.
    if "unit " in q_lower:
        for m in re.finditer(
            r"\bunit\s+([a-z][a-z'\-]{3,}(?:\s+[a-z][a-z'\-]{3,}){0,4})\b",
            question,
            re.IGNORECASE,
        ):
            phrases.append(m.group(1).strip())

    # "X or Y", "X vs Y", "X versus Y" — extracts both subjects even when lowercase.
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

    # "between X and Y" — covers "difference between X and Y" questions.
    # Non-greedy so it snaps to the nearest "and", not words before both subjects.
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

    # "X and Y" when the question signals a comparison/relationship.
    # Restricted to single-word subjects to avoid over-greedily matching whole clauses.
    if any(sig in q_lower for sig in _COMPARISON_SIGNALS):
        for m in re.finditer(
            r"\b([A-Za-z][A-Za-z'\-]{3,})\s+and\s+([A-Za-z][A-Za-z'\-]{3,})\b",
            question,
            re.IGNORECASE,
        ):
            for grp in (m.group(1).strip(), m.group(2).strip()):
                if _normalize(grp) not in _FILTER_WORDS:
                    phrases.append(grp)

    # Bare lowercase nouns when a game property word is present.
    # Catches questions like "how many attacks do plague marines have?" where
    # the unit name is all-lowercase. Single-word matches only; the heading
    # search's token-overlap scoring then reunites related words (e.g. "plague"
    # + "marines" both independently score well against "### Plague Marines").
    if any(kw in q_lower for kw in _GAME_PROPERTY_WORDS):
        for m in re.finditer(r"\b([a-z][a-z'\-]{3,})\b", question):
            candidate = m.group(1).strip()
            norm = _normalize(candidate)
            if norm not in _GAME_PROPERTY_STOP and not any(
                norm == _normalize(p) for p in phrases
            ):
                phrases.append(candidate)

    # Deduplicate, preserve order, drop very short entries.
    seen: set = set()
    result: List[str] = []
    for p in phrases:
        key = _normalize(p)
        if len(p) >= 4 and key not in seen:
            seen.add(key)
            result.append(p)

    return result


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


# ---------------------------------------------------------------------------
# Main QA function
# ---------------------------------------------------------------------------

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
    # 1. Semantic retrieval.
    context_snippets = retrieve_context(vectorstore, question, k=k)

    # 2. Keyword retrieval (augments semantic search for specific unit/ability lookups).
    keyword_snippets: List[str] = []
    sources = rules_sources
    phrases = None

    if sources is None and data_dir:
        phrases = extract_candidate_phrases(question)
        if phrases:
            sources = load_rules_sources(data_dir)

    if sources:
        if phrases is None:
            phrases = extract_candidate_phrases(question)
        if phrases:
            max_kw = min(6, max(3, len(phrases)))
            keyword_snippets = find_keyword_snippets(
                sources, question, phrases,
                max_snippets=max_kw,
                heading_vocab=heading_vocab,
            )

    # Reduce semantic noise when keyword search already covers all subjects with
    # precise points data. If only a subset of subjects is covered, keep more
    # semantic chunks so the remaining subjects can still be found.
    prefer_points = any(kw in question.lower() for kw in ("point", "points", "pts"))
    if prefer_points and keyword_snippets:
        points_found = sum(1 for s in keyword_snippets if "**Points:**" in s)
        num_subjects = len(phrases) if phrases else 1
        if points_found >= num_subjects:
            context_snippets = context_snippets[:3]
        elif points_found > 0:
            context_snippets = context_snippets[:6]

    # Keyword snippets go first so the model sees the most precise matches upfront.
    all_snippets = keyword_snippets + context_snippets
    context_block = "\n\n---\n\n".join(all_snippets)

    llm = ChatOpenAI(model=model_name, temperature=0.2)

    messages = [
        (
            "system",
            f"{system_prompt}\n\nYou are answering rules questions for: {game_label}.",
        ),
        (
            "system",
            "Below is the relevant rules context retrieved from the selected game's "
            "rules files. Answer ONLY using information that appears here.\n\n"
            f"{context_block}",
        ),
        ("user", question),
    ]

    response = llm.invoke(messages)
    return response.content.strip()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

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
