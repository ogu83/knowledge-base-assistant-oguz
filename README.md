# Knowledge Base Assistant – Backend

FastAPI + PostgreSQL backend for the Intelligent Knowledge Base Assistant.

## Prerequisites
- Python 3.10+
- PostgreSQL 13+ reachable at your configured host
- (Optional) `psql` CLI for troubleshooting

## Quick Start

### 1) Clone & enter the backend folder
```bash
# Example path - adjust to your setup
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
    schema.sql      # Tables, indexes, triggers for FTS + category/date index
.env.example        # Sample env config (at repo root)
```

## Troubleshooting
- **Cannot create database / transaction error**: `CREATE DATABASE` must run outside a transaction. Ensure the initializer uses autocommit when connecting to the `postgres` DB.
- **File not found (schema.sql)**: Run `python init_db.py` from the `backend` directory so the relative `data/schema.sql` path resolves.
- **Connection refused**: Verify host/port/credentials, and that PostgreSQL accepts connections from your machine.

## Next Steps
- Add `llm.py` with OpenAI integration and token budgeting.
- Add README notes for indexing performance and query plans.
- Optionally add `docker-compose.yml` for Postgres + API.