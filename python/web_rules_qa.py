"""
FastAPI web wrapper for the Warhammer Rules RAG engine.

This exposes a minimal endpoint used by the Laravel app:
    POST /ask

Request body:
    { "question": "...", "game": "aos" | "wh40k" }
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from rag_engine import (
    DEFAULT_AOS_DATA_DIR,
    DEFAULT_AOS_INDEX_DIR,
    DEFAULT_WH40K_DATA_DIR,
    DEFAULT_WH40K_INDEX_DIR,
    SYSTEM_PROMPT,
    answer_question,
    build_heading_vocabulary,
    load_index,
    load_rules_sources,
)

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

_VECTORSTORES = {}
_SOURCES: dict[str, list[tuple[str, str]]] = {}
_HEADING_VOCABS: dict[str, list[tuple[str, str]]] = {}
_STARTUP_ERRORS: dict[str, str] = {}
_GAME_LABELS = {
    "aos": "Warhammer Age of Sigmar",
    "wh40k": "Warhammer 40,000",
}


def _load_game_resources(game: str, index_dir: str, data_dir: str) -> None:
    try:
        _VECTORSTORES[game] = load_index(index_dir=index_dir)
        _SOURCES[game] = load_rules_sources(data_dir)
        _HEADING_VOCABS[game] = build_heading_vocabulary(_SOURCES[game])
        _STARTUP_ERRORS.pop(game, None)
    except SystemExit as exc:
        _VECTORSTORES.pop(game, None)
        _SOURCES.pop(game, None)
        _HEADING_VOCABS.pop(game, None)
        _STARTUP_ERRORS[game] = str(exc)
    except Exception as exc:
        _VECTORSTORES.pop(game, None)
        _SOURCES.pop(game, None)
        _HEADING_VOCABS.pop(game, None)
        _STARTUP_ERRORS[game] = f"{type(exc).__name__}: {exc}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_game_resources("aos", DEFAULT_AOS_INDEX_DIR, DEFAULT_AOS_DATA_DIR)
    _load_game_resources("wh40k", DEFAULT_WH40K_INDEX_DIR, DEFAULT_WH40K_DATA_DIR)
    yield


app = FastAPI(title="Warhammer Rules RAG API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str
    game: Literal["aos", "wh40k"]


class AskResponse(BaseModel):
    short_answer: str
    detailed_answer: str
    source: str
    certainty: int = 4


_CORE_RULE_LABELS = {
    "aos": "WH Age of Sigmar Core Rules (4th ed.)",
    "wh40k": "WH 40.000 Core Rules (10th ed.)",
}

_FACTION_SUFFIXES = {
    "aos": "Battletome",
    "wh40k": "Codex",
}

def _clean_answer_text(text: str) -> str:
    return text.replace('\\"', '"')


def _format_source(game: str, has_core_rules: bool, factions: list) -> str:
    parts = []
    if has_core_rules:
        parts.append(_CORE_RULE_LABELS.get(game, "Core Rules"))
    suffix = _FACTION_SUFFIXES.get(game, "Rulebook")
    for faction in factions:
        parts.append(f"{faction} {suffix}")
    return " & ".join(parts)


def _parse_answer(raw: str, game: str) -> AskResponse:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        raw = raw.rsplit("```", 1)[0]
    try:
        data = json.loads(raw)
        source_raw = data.get("source", {})
        if isinstance(source_raw, dict):
            source_str = _format_source(
                game,
                bool(source_raw.get("has_core_rules", False)),
                list(source_raw.get("factions", [])),
            )
        else:
            source_str = str(source_raw)
        certainty_raw = data.get("certainty", 4)
        try:
            certainty = max(1, min(4, int(certainty_raw)))
        except (TypeError, ValueError):
            certainty = 4
        return AskResponse(
            short_answer=_clean_answer_text(data.get("short_answer", "")),
            detailed_answer=_clean_answer_text(data.get("detailed_answer", "")),
            source=source_str,
            certainty=certainty,
        )
    except (json.JSONDecodeError, ValueError):
        return AskResponse(short_answer=raw, detailed_answer="", source="")


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    question = (req.question or "").strip()
    if not question:
        raise HTTPException(status_code=422, detail="Question is required.")

    vectorstore = _VECTORSTORES.get(req.game)
    sources = _SOURCES.get(req.game)
    vocab = _HEADING_VOCABS.get(req.game)
    if vectorstore is None or sources is None or vocab is None:
        detail = _STARTUP_ERRORS.get(req.game, "Rules resources are not loaded.")
        raise HTTPException(status_code=503, detail=detail)

    try:
        raw = answer_question(
            question=question,
            vectorstore=vectorstore,
            game_label=_GAME_LABELS[req.game],
            system_prompt=SYSTEM_PROMPT,
            rules_sources=sources,
            heading_vocab=vocab,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="AI service failed while generating an answer.",
        ) from exc

    return _parse_answer(raw, req.game)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8001)

