import logging
import re
import time
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator

from dotenv import load_dotenv
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

from db import USE_INDEXES, query  # uses env vars; parameterized queries for safety
from llm import generate_answer    # reads OPENAI_API_KEY/OPENAI_MODEL from .env

# ---------------- Logging ----------------
logger = logging.getLogger("kba.api")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

app = FastAPI(title="Knowledge Base Assistant - Backend")

# ---------------- CORS ----------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten for prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- Validation / Sanitizers ----------------
MAX_QUERY_LEN = 200
MAX_CATEGORY_LEN = 50
MAX_LIMIT = 50
MAX_CTX_IDS = 16
SAFE_TEXT_RE = re.compile(r"[^A-Za-z0-9_\-\s\.,:+#()/]")

def sanitize_text(val: str, max_len: int) -> str:
    if val is None:
        return ""
    val = val.strip()
    if len(val) > max_len:
        val = val[:max_len]
    # remove characters outside a conservative allow-list
    return SAFE_TEXT_RE.sub("", val)

class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=1000)
    context_ids: List[int] = Field(..., min_items=1)
    
    @validator("context_ids")
    def ctx_ids_rules(cls, v):
        if len(v) > MAX_CTX_IDS:
            raise ValueError(f"Too many context_ids (>{MAX_CTX_IDS}).")
        if any((not isinstance(x, int) or x <= 0) for x in v):
            raise ValueError("context_ids must be positive integers.")
        return v

# ---------------- Routes ----------------
@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/api/search")
def search(
    q: str = Query(..., alias="query"),
    category: Optional[str] = None,
    limit: int = 5
):
    # Input validation / sanitation
    if not isinstance(q, str) or not q.strip():
        raise HTTPException(status_code=400, detail="query is required")
    q = sanitize_text(q, MAX_QUERY_LEN)
    if category is not None:
        category = sanitize_text(category, MAX_CATEGORY_LEN) or None
    if not isinstance(limit, int) or limit < 1 or limit > MAX_LIMIT:
        raise HTTPException(status_code=400, detail=f"limit must be between 1 and {MAX_LIMIT}")

    start_total = time.perf_counter()

    if USE_INDEXES:
        # Indexed path: filter with substring semantics (ILIKE) accelerated by trigram indexes,
        # and rank results using FTS (materialized search_vector or fallback).
        fts_q = q  # used only for ranking via websearch_to_tsquery
        sql = """
        SELECT
            a.id,
            a.title,
            left(a.content, 280) AS excerpt,
            a.publish_date,
            au.id AS author_id,
            au.name AS author_name,
            au.bio AS author_bio,
            c.id AS category_id,
            c.name AS category_name,
            COALESCE(string_agg(t.name, ', ' ORDER BY t.name), '') AS tags,
            ts_rank(
            COALESCE(
                a.search_vector,
                setweight(to_tsvector('english', coalesce(a.title,'')), 'A') ||
                setweight(to_tsvector('english', coalesce(a.content,'')), 'B')
            ),
            websearch_to_tsquery('english', %s)
            ) AS rank
        FROM articles a
        JOIN authors au ON au.id = a.author_id
        JOIN categories c ON c.id = a.category_id
        LEFT JOIN article_tags at ON at.article_id = a.id
        LEFT JOIN tags t ON t.id = at.tag_id
        WHERE (a.title ILIKE %s OR a.content ILIKE %s)
        AND (%s IS NULL OR c.name = %s)
        GROUP BY a.id, au.id, c.id
        ORDER BY rank DESC, a.publish_date DESC
        LIMIT %s
        """
        params = (fts_q, f'%{q}%', f'%{q}%', category, category, limit)
    else:
        # No-index baseline: ILIKE only (slow but correct).
        sql = '''
        SELECT
            a.id,
            a.title,
            left(a.content, 280) AS excerpt,
            a.publish_date,
            au.id AS author_id,
            au.name AS author_name,
            au.bio AS author_bio,
            c.id AS category_id,
            c.name AS category_name,
            COALESCE(string_agg(t.name, ', ' ORDER BY t.name), '') AS tags,
            0.0::float AS rank
        FROM articles a
        JOIN authors au ON au.id = a.author_id
        JOIN categories c ON c.id = a.category_id
        LEFT JOIN article_tags at ON at.article_id = a.id
        LEFT JOIN tags t ON t.id = at.tag_id
        WHERE (a.title ILIKE %s OR a.content ILIKE %s)
        AND (%s IS NULL OR c.name = %s)
        GROUP BY a.id, au.id, c.id
        ORDER BY a.publish_date DESC
        LIMIT %s
        '''
        params = (f'%{q}%', f'%{q}%', category, category, limit)

    try:
        start_db = time.perf_counter()
        rows = query(sql, params)
        db_ms = (time.perf_counter() - start_db) * 1000.0
    except Exception:
        logger.exception("Search query failed")
        raise HTTPException(status_code=500, detail="Internal error while executing search.")

    total_ms = (time.perf_counter() - start_total) * 1000.0
    logger.info(
        "GET /api/search q=%r category=%r limit=%d -> rows=%d db_ms=%.2f total_ms=%.2f",
        q, category, limit, len(rows), db_ms, total_ms
    )

    return {
        "results": rows,
        "metrics": {
            "db_ms": round(db_ms, 2),
            "total_ms": round(total_ms, 2)
        }
    }

@app.post("/api/ask")
def ask(req: AskRequest):
    # Validate & sanitize question
    q = sanitize_text(req.question, 1000)
    if not q or len(q) < 3:
        raise HTTPException(status_code=400, detail="question is too short or empty")
    
    logging.info("POST /api/ask question=%r context_ids=%r", req.question, req.context_ids)

    sql_ctx = """
    SELECT id, title, content
    FROM articles
    WHERE id = ANY(%s)
    ORDER BY publish_date DESC
    """

    try:
        rows = query(sql_ctx, (req.context_ids,))
    except Exception:
        logger.exception("Context fetch failed")
        raise HTTPException(status_code=500, detail="Internal error while fetching context.")
    
    # Call LLM
    if not rows:
        raise HTTPException(status_code=400, detail="No articles found for given context_ids.")

    logging.info("Found %d context articles for IDs %r", len(rows), req.context_ids)

    try:
        answer = generate_answer(q, rows)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception:
        logger.exception("LLM generation failed")
        raise HTTPException(status_code=500, detail="Failed to generate answer.")

    return {"answer": answer, "used_article_ids": [r["id"] for r in rows]}
