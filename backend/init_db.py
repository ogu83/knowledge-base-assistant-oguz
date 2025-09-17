
"""
Initialize and seed the PostgreSQL database for the Knowledge Base Assistant.

Behavior:
- Ensures the target database exists (creates it if missing by connecting to the 'postgres' maintenance DB).
- Applies schema from ./data/schema.sql
- Seeds authors, categories, tags, and 20+ articles (idempotent: only inserts when empty).

Usage:
    python init_db.py

Relies on environment variables (or the defaults set in db.py):
    PG_HOST, PG_PORT, PG_USER, PG_PASSWORD, PG_DBNAME
"""
from __future__ import annotations

import os
import random
import datetime
from pathlib import Path

import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_values
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# Read connection defaults directly from db.py so env overrides still work there
from db import PG_HOST, PG_PORT, PG_USER, PG_PASSWORD, PG_DBNAME, USE_INDEXES

# Resolve schema path relative to this file (backend/data/schema.sql)
HERE = Path(__file__).resolve().parent
if not USE_INDEXES:
    print("ℹ USE_INDEXES is false; skipping index creation in schema.")
    SHEMA_FILE = "schema_no_index.sql"
else:
    print("ℹ USE_INDEXES is true; index creation will be applied in schema.")
    SHEMA_FILE = "schema.sql"
SCHEMA_PATH = HERE / "data" / SHEMA_FILE

authors_seed = [
    ("Guido Van Prime", "Engineer and writer focusing on Python internals."),
    ("Ada Data", "Database specialist with a love for SQL and query planning."),
    ("Grace Hopperton", "Backend engineer who cares about clarity and correctness."),
    ("Linus Craft", "Systems programmer exploring performance and tooling."),
]

categories_seed = ["Python", "Databases", "Frontend", "DevOps", "LLMs"]

tags_seed = [
    "asyncio", "typing", "indexes", "joins", "ORM", "transactions",
    "postgres", "sqlite", "fastapi", "flask", "testing", "cicd",
    "rag", "prompting", "vector", "tokenization", "performance", "caching"
]

article_titles = [
    "Mastering Async IO in Python",
    "Demystifying PostgreSQL Indexes",
    "Effective SQL Joins: Inner vs Outer",
    "FastAPI vs Flask: Choosing the Right Tool",
    "Schema Design for Scalable Apps",
    "Building RAG Pipelines without Heavy Frameworks",
    "Understanding Query Plans in Postgres",
    "Typing in Python: When and Why",
    "Full-Text Search with PostgreSQL",
    "Designing REST APIs for Performance",
    "Caching Strategies for Backend Services",
    "Migrations 101: Alembic and Beyond",
    "Testing Pyramid: Unit to E2E",
    "CI/CD for Python Backends",
    "Cursor vs Offset Pagination in APIs",
    "Transactions and Isolation Levels",
    "Secure Secrets: .env and Beyond",
    "Web Security Basics for APIs",
    "Vector Search vs Full-Text Search",
    "Prompt Engineering Essentials",
    "Token Budgets and Context Windows",
    "Frontend-Friendly API Responses",
    "Joins across Tags and Categories",
    "Date-based Partitioning in Postgres"
]

lorem = (
    "This article explores practical techniques with examples and trade-offs. "
    "It covers pitfalls, performance considerations, and real-world tips for teams. "
    "You will find code snippets, explanations, and gotchas to avoid in production. "
)

def _conn(dbname: str):
    return psycopg2.connect(
        host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASSWORD, dbname=dbname
    )

def ensure_database():
    """Ensure PG_DBNAME exists; create it if missing by connecting to 'postgres'."""
    import psycopg2

    try:
        with _conn(PG_DBNAME):
            print(f"✔ Database '{PG_DBNAME}' is reachable.")
            return
    except psycopg2.OperationalError as e:
        print(f"ℹ Target DB not reachable yet: {e}\nAttempting to create '{PG_DBNAME}'...")

    # Connect to maintenance DB and create target if missing
    conn = _conn("postgres")
    try:
        conn.autocommit = True  # <-- IMPORTANT: CREATE DATABASE must be autocommit
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (PG_DBNAME,))
            exists = cur.fetchone() is not None
            if not exists:
                from psycopg2 import sql
                cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(PG_DBNAME)))
                print(f"✔ Created database '{PG_DBNAME}'.")
            else:
                print(f"✔ Database '{PG_DBNAME}' already exists (creating not needed).")
    finally:
        conn.close()


def apply_schema_and_seed():
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Schema file not found at: {SCHEMA_PATH}")

    with _conn(PG_DBNAME) as conn:
        cur = conn.cursor()

        # Apply schema
        print(f"Applying schema from: {SCHEMA_PATH}")
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            cur.execute(f.read())
        conn.commit()

        # Insert authors
        cur.execute("SELECT COUNT(*) FROM authors")
        if cur.fetchone()[0] == 0:
            execute_values(cur, "INSERT INTO authors (name, bio) VALUES %s", authors_seed)

        # Insert categories
        cur.execute("SELECT COUNT(*) FROM categories")
        if cur.fetchone()[0] == 0:
            execute_values(cur, "INSERT INTO categories (name) VALUES %s", [(c,) for c in categories_seed])

        # Insert tags
        cur.execute("SELECT COUNT(*) FROM tags")
        if cur.fetchone()[0] == 0:
            execute_values(cur, "INSERT INTO tags (name) VALUES %s", [(t,) for t in tags_seed])

        # Maps
        cur.execute("SELECT id, name FROM categories")
        cat_map = {name: cid for cid, name in cur.fetchall()}
        cur.execute("SELECT id FROM authors")
        author_ids = [row[0] for row in cur.fetchall()]
        cur.execute("SELECT id, name FROM tags")
        tag_map = {name: tid for tid, name in cur.fetchall()}

        # Insert articles
        cur.execute("SELECT COUNT(*) FROM articles")
        if cur.fetchone()[0] == 0:
            articles = []
            today = datetime.date.today()
            for title in article_titles:
                content = (f"{title}\n\n" + lorem * random.randint(20, 40)).strip()
                publish_date = today - datetime.timedelta(days=random.randint(0, 900))
                author_id = random.choice(author_ids)
                category_id = cat_map[random.choice(list(cat_map.keys()))]
                articles.append((title, content, publish_date, author_id, category_id))

            execute_values(
                cur,
                "INSERT INTO articles (title, content, publish_date, author_id, category_id) VALUES %s",
                articles,
            )

            # Assign tags (2-5 tags per article)
            cur.execute("SELECT id FROM articles")
            article_ids = [row[0] for row in cur.fetchall()]
            at_rows = []
            tag_ids = list(tag_map.values())
            import random as _rnd
            for aid in article_ids:
                for tid in _rnd.sample(tag_ids, k=_rnd.randint(2, 5)):
                    at_rows.append((aid, tid))
            execute_values(
                cur,
                "INSERT INTO article_tags (article_id, tag_id) VALUES %s ON CONFLICT DO NOTHING",
                at_rows,
            )

        conn.commit()
        cur.close()
        print("✔ Schema applied and data seeded (idempotent).")


def main():
    print(f"Connecting to {PG_HOST}:{PG_PORT} as {PG_USER}, target DB='{PG_DBNAME}'")
    print(f"Schema path resolved to: {SCHEMA_PATH}")
    ensure_database()
    apply_schema_and_seed()
    print(f"✔ Done. Database '{PG_DBNAME}' ensured, schema applied, and data seeded.")

if __name__ == "__main__":
    main()
