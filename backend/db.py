
"""
Database connection and utilities for Knowledge Base Assistant.
Uses PostgreSQL with full-text search (tsvector) and GIN index.
"""

# ---------------- Postgres connection info ----------------
import os

PG_HOST = os.getenv("PG_HOST", "macbook-server")
PG_PORT = int(os.getenv("PG_PORT", 5432))
PG_USER = os.getenv("PG_USER", "postgres")
PG_PASSWORD = os.getenv("PG_PASSWORD", "Postgres2839*")
PG_DBNAME = os.getenv("PG_DBNAME", "KnowledgeBaseAssistant")
USE_INDEXES = os.getenv("USE_INDEXES", "false").lower() == "true"


import psycopg2
from psycopg2.extras import RealDictCursor

def get_conn():
    return psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        user=PG_USER,
        password=PG_PASSWORD,
        dbname=PG_DBNAME,
    )

def query(sql, params=None):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params or ())
            if cur.description:
                return cur.fetchall()
            return []

def execute(sql, params=None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            conn.commit()
