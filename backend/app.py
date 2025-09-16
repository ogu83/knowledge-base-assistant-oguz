
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
from fastapi.middleware.cors import CORSMiddleware
from db import query

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
    # Full-text search across title+content using ts_rank
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
        ts_rank(a.search_vector, websearch_to_tsquery('english', %s)) AS rank
    FROM articles a
    JOIN authors au ON au.id = a.author_id
    JOIN categories c ON c.id = a.category_id
    LEFT JOIN article_tags at ON at.article_id = a.id
    LEFT JOIN tags t ON t.id = at.tag_id
    WHERE a.search_vector @@ websearch_to_tsquery('english', %s)
      AND (%s IS NULL OR c.name = %s)
    GROUP BY a.id, au.id, c.id
    ORDER BY rank DESC, a.publish_date DESC
    LIMIT %s
    '''
    params = (q, q, category, category, limit)
    rows = query(sql, params)
    return {"results": rows}

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
