# Knowledge Base Assistant – Backend

FastAPI + PostgreSQL backend for the Intelligent Knowledge Base Assistant.

## Prerequisites
- Python 3.10+
- PostgreSQL 13+ reachable at your configured host
- (Optional) `psql` CLI for troubleshooting

## Quick Start

### 1) Clone & enter the backend folder
```bash
cd knowledge-base-assistant-oguz/backend
```

### 2) Create and activate a virtual environment

**Windows (PowerShell)**
```powershell
python -m venv venv
.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

**Linux / macOS**
```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3) Configure environment variables
Create a `.env` in the repo root (sibling to `backend/`) or export env vars in your shell. A template is provided as `.env.example`.

Defaults (used if env vars are not set) are:
```
PG_HOST=macbook-server
PG_PORT=5432
PG_USER=postgres
PG_PASSWORD=Postgres2839*
PG_DBNAME=KnowledgeBaseAssistant
USE_INDEXES=true
```

### 4) Initialize the database (auto-create + schema + seed)
From the **backend** folder:
```bash
# Windows PowerShell or Linux/macOS (after activating venv)
python init_db.py
```
This will:
- Ensure the database exists (create if missing by connecting to the `postgres` maintenance DB).
- Apply `./data/schema.sql`.
- Seed authors, categories, tags, and sample articles (idempotent).

### 5) Run the API
```bash
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```
Health check: http://localhost:8000/health  
Search endpoint example: `GET /api/search?query=mastering`

## Project Structure
```
backend/
  app.py            # FastAPI app: /health, /api/search, /api/ask (LLM stub)
  db.py             # PG connection + simple query helpers
  init_db.py        # Creates DB if missing, applies schema, seeds data
  requirements.txt  # Python deps
  data/
    schema.sql               # Tables, indexes, triggers for FTS + category/date index
    schema_no_index.sql      # Tables and releations only
.env.example        # Sample env config (at repo root)
```

## Troubleshooting
- **Cannot create database / transaction error**: `CREATE DATABASE` must run outside a transaction. Ensure the initializer uses autocommit when connecting to the `postgres` DB.
- **File not found (schema.sql)**: Run `python init_db.py` from the `backend` directory so the relative `data/schema.sql` path resolves.
- **Connection refused**: Verify host/port/credentials, and that PostgreSQL accepts connections from your machine.

## Indexing & Performance Gain for Database Queries
### Search Performance & Indexing Notes

This section summarizes the search performance of the `/api/search` endpoint **with** and **without** indexes, and explains each index used and why it helps.

The API itself logs and returns timing metrics (`db_ms`, `total_ms`) for each search query. See the FastAPI handler in `app.py` for details:contentReference[oaicite:0]{index=0}. The database schema applied depends on the `USE_INDEXES` flag in `.env`:contentReference[oaicite:1]{index=1}, as handled in `init_db.py`:contentReference[oaicite:2]{index=2}.

### How the benchmark was run

- Endpoint: `GET /api/search?query=SQL`
- Dataset: Seeded by `init_db.py` (24 articles with tags).
- Two runs:
  1. **Without indexes** – baseline using substring search (`ILIKE`).  
  2. **With indexes** – using FTS + trigram indexes for filtering and ranking.

### Results (example run)
**Request** 
```
http://localhost:8000/api/search?query=SQL
```

With Indexes:
```json
{
  "results": [
    {
      "id": 3,
      "title": "Effective SQL Joins: Inner vs Outer",
        ....
    },
    {
      "id": 9,
      "title": "Full-Text Search with PostgreSQL",
      ....
    },
    {
      "id": 2,
      "title": "Demystifying PostgreSQL Indexes",
        ....
    }
  ],
  "metrics": {
    "db_ms": 90,
    "total_ms": 90.01
  }
}
```

Without Indexes:
```json
{
  "results": [
    {
      "id": 9,
      "title": "Full-Text Search with PostgreSQL",
      ....
    },
    {
      "id": 3,
      "title": "Effective SQL Joins: Inner vs Outer",
      ....
    },
    {
      "id": 2,
      "title": "Demystifying PostgreSQL Indexes",
       ....
    }
  ],
  "metrics": {
    "db_ms": 129.36,
    "total_ms": 129.36
  }
}
```

On this dataset and query, indexes reduced database execution time from ~129.36 ms to ~90 ms (≈ 30% faster).
As the corpus scales, the gap grows significantly because indexes avoid full table scans and expensive text processing.

### Indexes and why they help

#### Full-text search (FTS) GIN index

```sql
CREATE INDEX IF NOT EXISTS idx_articles_search_vector
  ON articles USING GIN (search_vector);
```
- `search_vector` stores a weighted `tsvector(title, content)` updated by a trigger.
- GIN allows `@@` matches (`to_tsquery`, `websearch_to_tsquery`) to skip scanning every row.
- Speeds up `ts_rank(search_vector, query)` ranking.

#### Trigger to keep `search_vector` updated

```sql
CREATE OR REPLACE FUNCTION articles_tsv_update() RETURNS trigger AS $$
BEGIN
  NEW.search_vector :=
    setweight(to_tsvector('english', coalesce(NEW.title,'')), 'A') ||
    setweight(to_tsvector('english', coalesce(NEW.content,'')), 'B');
  RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_articles_tsv_update ON articles;
CREATE TRIGGER trg_articles_tsv_update
BEFORE INSERT OR UPDATE ON articles
FOR EACH ROW EXECUTE FUNCTION articles_tsv_update();

-- Backfill existing rows
UPDATE articles SET title = title;
```
- Ensures the materialized `search_vector` is always in sync.
- Makes sure the FTS index is useful immediately after updates.

#### Composite index for category filtering + date sorting

```sql
CREATE INDEX IF NOT EXISTS idx_articles_category_date
  ON articles (category_id, publish_date);
```
- The API filters by category and sorts by publish date.
- This composite index supports that pattern directly, cutting sort/filter cost.

#### Trigram indexes for substring search (`ILIKE`)

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS idx_articles_title_trgm
  ON articles USING GIN (title gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_articles_content_trgm
  ON articles USING GIN (content gin_trgm_ops);
```

- Substring queries like `ILIKE '%SQL%'` match “PostgreSQL”.
- Trigram indexes make these substring searches fast (otherwise they require sequential scans).
- Preserves recall identical to the baseline but with large performance gains.

## Next Steps
- Add `llm.py` with OpenAI integration and token budgeting.
- Add README notes for indexing performance and query plans.
- Optionally add `docker-compose.yml` for Postgres + API.