
-- Schema for Knowledge Base Assistant (PostgreSQL)

CREATE TABLE IF NOT EXISTS authors (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    bio TEXT
);

CREATE TABLE IF NOT EXISTS categories (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS articles (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    publish_date DATE NOT NULL,
    author_id INTEGER NOT NULL REFERENCES authors(id) ON DELETE CASCADE,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
    search_vector tsvector
);

CREATE TABLE IF NOT EXISTS tags (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS article_tags (
    article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (article_id, tag_id)
);

-- Indexes
-- Full-text search GIN index
CREATE INDEX IF NOT EXISTS idx_articles_search_vector ON articles USING GIN (search_vector);

-- Composite index for category + publish_date (common filtering/sorting pattern)
CREATE INDEX IF NOT EXISTS idx_articles_category_date ON articles (category_id, publish_date);

-- Trigger to keep search_vector in sync
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

-- Backfill existing rows (force trigger to run)
UPDATE articles SET title = title;

-- Enable trigram search (once per DB)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Trigram indexes to accelerate substring search
CREATE INDEX IF NOT EXISTS idx_articles_title_trgm
  ON articles USING GIN (title gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_articles_content_trgm
  ON articles USING GIN (content gin_trgm_ops);
