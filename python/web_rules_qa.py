"""
FastAPI web wrapper for the Warhammer Rules RAG engine.

Right now the endpoint focuses on input validation + wiring.
Response content will be implemented later.
"""

from __future__ import annotations

import os
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

app = FastAPI(title="Warhammer Rules RAG API")

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
    """
    Accepts:
        {
          "question": "...",
          "game": "aos" | "wh40k"
        }

    For now, we only acknowledge the request. Later we will call into
    `rag_engine.py` and return a real model answer.
    """
    # Basic sanity: avoid returning empty content to the frontend later.
    question = (req.question or "").strip()
    if not question:
        return AskResponse(answer="")  # TODO: replace with proper validation/error

    # TODO: plug into rag_engine.py for real answers.
    return AskResponse(answer="")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)

