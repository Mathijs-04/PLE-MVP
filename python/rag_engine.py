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

    # Two or more consecutive Title-Case words (typical unit/ability names).
    for m in re.finditer(r"([A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+)+)", question):
        phrases.append(m.group(1).strip())

    # Single long Title-Case token (e.g. "Mirrorshield", "DeepStrike").
    for m in re.finditer(r"\b([A-Z][A-Za-z]{3,})\b", question):
        phrases.append(m.group(1).strip())

    # Lowercase "unit <name>" fallback.
    if "unit " in q_lower:
        for m in re.finditer(
            r"\bunit\s+([a-z][a-z'\-]{3,}(?:\s+[a-z][a-z'\-]{3,}){0,4})\b",
            question,
            re.IGNORECASE,
        ):
            phrases.append(m.group(1).strip())

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
) -> List[str]:
    """
    For each extracted candidate phrase, try a structure-aware heading match first,
    then fall back to a sliding-window keyword match.
    """
    q_lower = question.lower()
    prefer_points = any(kw in q_lower for kw in ("point", "points", "pts"))

    out: List[str] = []
    for phrase in phrases:
        if len(out) >= max_snippets:
            break

        sections = _heading_keyword_search(sources, phrase, prefer_points=prefer_points, max_results=1)
        if sections:
            out.extend(sections)
            continue

        windows = _window_keyword_search(
            sources, phrase, prefer_points=prefer_points, window=window, max_results=1
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
) -> str:
    """
    Retrieve relevant rules context and ask the chat model to answer the question.

    Args:
        question:     The user's rules question.
        vectorstore:  Pre-loaded FAISS index for the target game.
        game_label:   Human-readable game name ("Warhammer Age of Sigmar", etc.)
        data_dir:     Path to the markdown files (enables keyword search). Optional.
        model_name:   OpenAI chat model identifier.
        system_prompt: Instructions for the model.
        k:            Number of semantic chunks to retrieve.

    Returns:
        The model's answer as a string.
    """
    # 1. Semantic retrieval.
    context_snippets = retrieve_context(vectorstore, question, k=k)

    # 2. Keyword retrieval (augments semantic search for specific unit/ability lookups).
    keyword_snippets: List[str] = []
    if data_dir:
        phrases = extract_candidate_phrases(question)
        if phrases:
            sources = load_rules_sources(data_dir)
            keyword_snippets = find_keyword_snippets(sources, question, phrases)

    # If we found a precise points block, reduce noise from semantic results.
    prefer_points = any(kw in question.lower() for kw in ("point", "points", "pts"))
    if prefer_points and any("**Points:**" in s for s in keyword_snippets):
        context_snippets = context_snippets[:3]

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
