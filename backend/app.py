
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
from fastapi.middleware.cors import CORSMiddleware
import logging
import time

from dotenv import load_dotenv
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

from db import USE_INDEXES, query

logger = logging.getLogger("kba.api")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

app = FastAPI(title="Knowledge Base Assistant - Backend")

# CORS (adjust as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AskRequest(BaseModel):
    question: str
    context_ids: List[int]

@app.get("/health")
def health():
    return {"status": "ok"}

def build_prefix_tsquery(user_text: str) -> str:
    # very simple sanitizer: keep letters, digits, and spaces; split into terms
    import re
    terms = [t for t in re.split(r"\s+", re.sub(r"[^A-Za-z0-9\s]+", " ", user_text).strip()) if t]
    if not terms:
        return ""  # caller should handle empty
    # join terms with AND and prefix operator :*
    return " & ".join(f"{t}:*" for t in terms)

@app.get("/api/search")
def search(
    q: str = Query(..., alias="query"),
    category: Optional[str] = None,
    limit: int = 5
):
    start_total = time.perf_counter()

    if USE_INDEXES:
        # With indexes, we can use full-text search efficiently
        # Full-text search across title+content using ts_rank
        fts_q = q  # you can keep build_prefix_tsquery if you prefer
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

    start_db = time.perf_counter()
    rows = query(sql, params)
    db_ms = (time.perf_counter() - start_db) * 1000.0
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
    # Retrieve contexts (keep under ~1000-1500 words for now; LLM integration comes next)
    if not req.context_ids:
        raise HTTPException(status_code=400, detail="context_ids is required")
    sql_ctx = '''
    SELECT id, title, content
    FROM articles
    WHERE id = ANY(%s)
    ORDER BY publish_date DESC
    '''
    rows = query(sql_ctx, (req.context_ids,))
    # Concatenate a trimmed context (naive token approx via words)
    def trim(text, max_words=500):
        words = text.split()
        return " ".join(words[:max_words])
    context = []
    for r in rows:
        context.append(f"# {r['title']}\n\n" + trim(r["content"], 500))
    combined = "\n\n---\n\n".join(context)
    # TODO: Replace this stub with actual LLM call (OpenAI) in llm.py
    answer = f"(LLM stub) Would answer the question using {len(combined.split())} words of context."
    return {"answer": answer, "used_article_ids": [r["id"] for r in rows]}
