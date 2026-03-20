"""
Build FAISS vector indexes from Warhammer rules markdown files.

Usage:
    python build_index.py --game aos
    python build_index.py --game wh40k
    python build_index.py --game aos --game wh40k   (both at once)
    python build_index.py --game aos --data-dir /custom/path --index-dir /custom/index

The script reads all .md files in the configured data directory, splits them into
semantically coherent chunks (first by markdown headers, then by character count),
embeds them with OpenAI's text-embedding-3-small model, and saves a FAISS index to disk.

Requires OPENAI_API_KEY in the environment or a .env file in the project root.
"""

import argparse
import os
import re
from typing import List, Tuple

from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

# Paths are relative to this script's location (python/)
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)

DEFAULT_WH40K_DATA_DIR = os.path.join(_PROJECT_ROOT, "data", "datafiles-WH40K")
DEFAULT_WH40K_INDEX_DIR = os.path.join(_HERE, "indexes", "40k")

DEFAULT_AOS_DATA_DIR = os.path.join(_PROJECT_ROOT, "data", "datafiles-WHAOS")
DEFAULT_AOS_INDEX_DIR = os.path.join(_HERE, "indexes", "aos")

EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_CHUNK_SIZE = 1200
DEFAULT_CHUNK_OVERLAP = 200


def iter_markdown_files(data_dir: str) -> List[str]:
    if not os.path.isdir(data_dir):
        raise SystemExit(f"Data directory not found: {data_dir}")

    paths = sorted(
        os.path.join(data_dir, f)
        for f in os.listdir(data_dir)
        if f.lower().endswith(".md")
    )

    if not paths:
        raise SystemExit(f"No markdown files found in: {data_dir}")

    return paths


def infer_doc_metadata(md_path: str, game: str) -> Tuple[str, str | None]:
    """
    Return (doc_kind, faction) based on the filename.

    doc_kind is one of: "core_rules", "faction_rules", "supplement"
    faction is None for core rules and supplements.
    """
    stem = os.path.splitext(os.path.basename(md_path))[0].strip()
    stem_lower = stem.lower()

    if "core" in stem_lower and "rule" in stem_lower:
        return "core_rules", None

    if game == "aos":
        if stem_lower in {"lores", "regiments of renown"}:
            return "supplement", None
        if stem_lower.startswith("path to glory"):
            return "supplement", None

    return "faction_rules", stem


def split_markdown_to_documents(
    md_text: str,
    *,
    source_path: str,
    game: str,
    doc_kind: str,
    faction: str | None,
    chunk_size: int,
    chunk_overlap: int,
) -> List[Document]:
    """
    Split a markdown file into chunks while preserving document structure.

    First splits by markdown headers so each chunk stays within a section,
    then further splits by character count if sections are still too large.
    """
    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[
            ("#", "h1"),
            ("##", "h2"),
            ("###", "h3"),
            ("####", "h4"),
        ]
    )
    header_docs = header_splitter.split_text(md_text)

    char_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", " ", ""],
    )

    documents: List[Document] = []
    for header_doc in header_docs:
        meta = dict(header_doc.metadata or {})
        meta.update({"source": source_path, "game": game, "doc_kind": doc_kind})
        if faction:
            meta["faction"] = faction

        for chunk_text in char_splitter.split_text(header_doc.page_content):
            content = chunk_text.strip()
            if content:
                documents.append(Document(page_content=content, metadata=meta))

    return documents


def build_index(
    data_dir: str,
    index_dir: str,
    game: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> None:
    """
    Build a FAISS index from all markdown files in data_dir and save it to index_dir.
    """
    md_paths = iter_markdown_files(data_dir)
    game_label = "Age of Sigmar" if game == "aos" else "Warhammer 40,000"

    print(f"[{game_label}] Building index from {len(md_paths)} files in: {data_dir}")

    documents: List[Document] = []
    for path in md_paths:
        with open(path, "r", encoding="utf-8") as f:
            md_text = f.read()

        doc_kind, faction = infer_doc_metadata(path, game=game)
        documents.extend(
            split_markdown_to_documents(
                md_text,
                source_path=path,
                game=game,
                doc_kind=doc_kind,
                faction=faction,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
        )

    print(f"[{game_label}] Embedding {len(documents)} chunks...")

    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    vectorstore = FAISS.from_documents(documents, embedding=embeddings)

    os.makedirs(index_dir, exist_ok=True)
    vectorstore.save_local(index_dir)

    print(f"[{game_label}] Saved FAISS index to: {index_dir}")


def main() -> int:
    load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))

    parser = argparse.ArgumentParser(
        description="Build FAISS vector indexes from Warhammer rules markdown files."
    )
    parser.add_argument(
        "--game",
        choices=["aos", "wh40k"],
        action="append",
        dest="games",
        required=True,
        help="Game system to index. Can be specified multiple times to build both.",
    )
    parser.add_argument(
        "--data-dir",
        help="Override the markdown source directory (applies when indexing a single game).",
    )
    parser.add_argument(
        "--index-dir",
        help="Override the FAISS index output directory (applies when indexing a single game).",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=DEFAULT_CHUNK_SIZE,
        help=f"Maximum characters per chunk (default: {DEFAULT_CHUNK_SIZE}).",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=DEFAULT_CHUNK_OVERLAP,
        help=f"Character overlap between consecutive chunks (default: {DEFAULT_CHUNK_OVERLAP}).",
    )

    args = parser.parse_args()

    if len(args.games) > 1 and (args.data_dir or args.index_dir):
        parser.error("--data-dir / --index-dir can only be used when building a single game.")

    for game in args.games:
        if game == "aos":
            data_dir = args.data_dir or DEFAULT_AOS_DATA_DIR
            index_dir = args.index_dir or DEFAULT_AOS_INDEX_DIR
        else:
            data_dir = args.data_dir or DEFAULT_WH40K_DATA_DIR
            index_dir = args.index_dir or DEFAULT_WH40K_INDEX_DIR

        build_index(
            data_dir=data_dir,
            index_dir=index_dir,
            game=game,
            chunk_size=args.chunk_size,
            chunk_overlap=args.chunk_overlap,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
