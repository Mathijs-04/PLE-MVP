"""
FastAPI web wrapper for the Warhammer Rules RAG engine.

This exposes a minimal endpoint used by the Laravel app:
    POST /ask

Request body:
    { "question": "...", "game": "aos" | "wh40k" }
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI
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
_GAME_LABELS = {
    "aos": "Warhammer Age of Sigmar",
    "wh40k": "Warhammer 40,000",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    _VECTORSTORES["aos"] = load_index(index_dir=DEFAULT_AOS_INDEX_DIR)
    _VECTORSTORES["wh40k"] = load_index(index_dir=DEFAULT_WH40K_INDEX_DIR)
    _SOURCES["aos"] = load_rules_sources(DEFAULT_AOS_DATA_DIR)
    _SOURCES["wh40k"] = load_rules_sources(DEFAULT_WH40K_DATA_DIR)
    _HEADING_VOCABS["aos"] = build_heading_vocabulary(_SOURCES["aos"])
    _HEADING_VOCABS["wh40k"] = build_heading_vocabulary(_SOURCES["wh40k"])
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
    answer: str


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    question = (req.question or "").strip()
    if not question:
        return AskResponse(answer="")

    vectorstore = _VECTORSTORES.get(req.game)
    sources = _SOURCES.get(req.game)
    vocab = _HEADING_VOCABS.get(req.game)
    if vectorstore is None:
        return AskResponse(answer="")

    answer = answer_question(
        question=question,
        vectorstore=vectorstore,
        game_label=_GAME_LABELS[req.game],
        system_prompt=SYSTEM_PROMPT,
        rules_sources=sources,
        heading_vocab=vocab,
    )
    return AskResponse(answer=answer)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8001)

