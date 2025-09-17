
"""
llm.py - Minimal OpenAI integration for Knowledge Base Assistant.

- No heavy frameworks; hand-rolled prompt + context handling
- Uses a rough token proxy via len(text.split())
- Summarizes context if over budget
- Reads OPENAI_API_KEY and OPENAI_MODEL from .env at repo root

Requirements:
  openai
  python-dotenv
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Iterable, List
from pathlib import Path

from dotenv import load_dotenv

# Load .env from repo root (../.env relative to this file)
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

try:
    from openai import OpenAI
except Exception:
    OpenAI = None  # provide nicer error if lib is missing

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
API_KEY = os.getenv("OPENAI_API_KEY", "")

WORD_BUDGET = 3500   # ~4k token ballpark for gpt-3.5-turbo
CHUNK_WORDS = 400    # chunk size when splitting long articles
SUMMARY_TARGET = 150 # words per article during summarization

logger = logging.getLogger("kba.api")

def _approx_words(text: str) -> int:
    return len(text.split())

def _chunk(text: str, max_words: int) -> List[str]:
    words = text.split()
    return [" ".join(words[i:i+max_words]) for i in range(0, len(words), max_words)]

@dataclass
class Context:
    title: str
    body: str

def _rank_chunks(chunks: List[str], q: str) -> List[str]:
    q_terms = {w.lower() for w in q.split() if w}
    def score(c: str) -> int:
        return sum(1 for w in c.lower().split() if w in q_terms)
    return sorted(chunks, key=score, reverse=True)

def _build_prompt(question: str, contexts: List[Context]) -> str:
    sections = [f"# {c.title}\n\n{c.body}" for c in contexts]
    joined = "\n\n---\n\n".join(sections)
    system = (
        "You are a concise technical assistant. Use ONLY the provided context to answer. "
        "If the answer isn't in the context, say you don't have enough information. "
        "Keep answers under 200 words unless asked otherwise. Cite article titles inline when useful."
    )
    prompt = (
        f"{system}\n\n"
        f"Context:\n{joined}\n\n"
        f"Question: {question}\n"
        f"Answer:"
    )
    return prompt

def _ensure_client():
    if not API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set. Put it in your .env at repo root.")
    if OpenAI is None:
        raise RuntimeError("'openai' package not installed. Run: pip install openai")
    return OpenAI(api_key=API_KEY)

def summarize_long_context(question: str, contexts: List[Context]) -> List[Context]:
    client = _ensure_client()
    out: List[Context] = []
    for c in contexts:
        if _approx_words(c.body) <= SUMMARY_TARGET:
            out.append(c)
            continue
        prompt = (
            "Summarize the following article for answering the user question. "
            f"Write ~{SUMMARY_TARGET} words, keep key facts and technical details.\n\n"
            f"User question: {question}\n\n"
            f"Article titled: {c.title}\n\n"
            f"{c.body}"
        )
        resp = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": "You are a helpful technical summarizer."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        summary = (resp.choices[0].message.content or "").strip()
        out.append(Context(title=c.title, body=summary))
    return out

def generate_answer(question: str, raw_contexts: Iterable[dict]) -> str:
    """Return an answer using OpenAI, given rows with at least {title, content}."""
    # Build per-article top chunks
    contexts: List[Context] = []
    for row in raw_contexts:
        title = (row.get("title") or "").strip()
        content = (row.get("content") or "").strip()
        if not title or not content:
            continue
        chunks = _chunk(content, CHUNK_WORDS)
        top2 = _rank_chunks(chunks, question)[:2]
        contexts.append(Context(title=title, body=" ... ".join(top2)))

    # Trim to budget
    trimmed: List[Context] = []
    total_words = 0
    for c in contexts:
        w = _approx_words(c.body)
        if total_words + w > WORD_BUDGET:
            break
        trimmed.append(c)
        total_words += w

    # Summarize if still too big
    if total_words > WORD_BUDGET:
        trimmed = summarize_long_context(question, trimmed)


    logger.info("Using %d context articles (~%d words) for question %r",
            len(trimmed), sum(_approx_words(c.body) for c in trimmed), question)
    
    # logger.info("API_KEY startswith: %.25s", API_KEY[:25] if API_KEY else None)

    # Build prompt + call OpenAI
    client = _ensure_client()
    prompt = _build_prompt(question, trimmed)
    resp = client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=[
            {"role": "system", "content": "You answer strictly from the provided documentation."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )
    return (resp.choices[0].message.content or "").strip()
