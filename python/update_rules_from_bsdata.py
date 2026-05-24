"""
Fetch BSData catalogs, convert them to markdown, and rebuild FAISS indexes.

End-to-end update wrapper around bsdata_importer and build_index.

Usage:
    python update_rules_from_bsdata.py --game wh40k
    python update_rules_from_bsdata.py --game aos --game wh40k
    python update_rules_from_bsdata.py --game wh40k --skip-index
    python update_rules_from_bsdata.py --game wh40k --dry-run

Requires OPENAI_API_KEY when rebuilding indexes (omit --skip-index).

See docs/data.md for folder layout, markdown format, and common workflows.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from bsdata_importer import REPOS, import_game
from build_index import (
    DEFAULT_AOS_INDEX_DIR,
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_WH40K_INDEX_DIR,
    build_index,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")

    parser = argparse.ArgumentParser(
        description="Fetch BSData catalogs, convert them to markdown, and rebuild FAISS indexes."
    )
    parser.add_argument(
        "--game",
        choices=["aos", "wh40k"],
        action="append",
        dest="games",
        required=True,
        help="Game system to update. Can be specified more than once.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Fetch and convert without writing markdown or indexes.")
    parser.add_argument("--skip-index", action="store_true", help="Write markdown without rebuilding FAISS indexes.")
    parser.add_argument("--limit-files", type=int, help="Fetch only the first N .cat files from each selected repo.")
    parser.add_argument("--repo-wh40k", help="Override the wh40k GitHub repo, for example owner/repo.")
    parser.add_argument("--repo-aos", help="Override the AoS GitHub repo, for example owner/repo.")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--chunk-overlap", type=int, default=DEFAULT_CHUNK_OVERLAP)
    args = parser.parse_args()

    for game in args.games:
        repo = args.repo_aos if game == "aos" else args.repo_wh40k
        result = import_game(
            game,
            dry_run=args.dry_run,
            skip_index=args.skip_index,
            limit_files=args.limit_files,
            repo=repo,
        )
        print(
            f"[{game}] fetched {result.source_count} .cat files, "
            f"generated {len(result.generated)} markdown files, "
            f"{'would write' if args.dry_run else 'wrote'} {len(result.written)} files"
        )
        if result.skipped:
            print(f"[{game}] skipped protected files: {', '.join(result.skipped)}")
        if result.preserved:
            print(f"[{game}] preserved {len(result.preserved)} existing markdown files")

        if args.dry_run or args.skip_index:
            continue

        if not os.getenv("OPENAI_API_KEY"):
            raise SystemExit("OPENAI_API_KEY is required to rebuild FAISS indexes. Re-run with --skip-index to only update markdown.")

        data_dir = REPOS[game]["data_dir"]
        index_dir = DEFAULT_AOS_INDEX_DIR if game == "aos" else DEFAULT_WH40K_INDEX_DIR
        build_index(
            data_dir=str(data_dir),
            index_dir=index_dir,
            game=game,
            chunk_size=args.chunk_size,
            chunk_overlap=args.chunk_overlap,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
