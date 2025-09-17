
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
from fastapi.middleware.cors import CORSMiddleware
import logging
import time
from llm import generate_answer

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
        fts_q = q  
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
    if not req.context_ids:
        raise HTTPException(status_code=400, detail="context_ids is required")
    
    sql_ctx = """
    SELECT id, title, content
    FROM articles
    WHERE id = ANY(%s)
    ORDER BY publish_date DESC
    """
    rows = query(sql_ctx, (req.context_ids,))

    try:
        answer = generate_answer(req.question, rows)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "answer": answer,
        "used_article_ids": [r["id"] for r in rows]
    }
