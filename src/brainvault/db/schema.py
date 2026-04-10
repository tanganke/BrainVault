"""Shared database schema for BrainVault (SQLite & PostgreSQL).

This module defines the canonical DDL statements and helper utilities
used by both :class:`~brainvault.db.sqlite.SQLiteAdapter` and
:class:`~brainvault.db.postgresql.PostgreSQLAdapter`.

Design goals:
- 99 % portable SQL so that both backends use the same schema.
- The tiny dialect differences (e.g. ``AUTOINCREMENT`` vs ``SERIAL``,
  ``TEXT`` vs ``VARCHAR``) are handled by parameter substitution.
"""

from __future__ import annotations

import hashlib
import re


# ---------------------------------------------------------------------------
# Core schema DDL (dialect-parameterised)
# ---------------------------------------------------------------------------

# Placeholders:
#   {autoincrement}  – "INTEGER PRIMARY KEY AUTOINCREMENT" (SQLite)
#                    – "SERIAL PRIMARY KEY"                (PostgreSQL)
#   {text_type}      – "TEXT" (SQLite) / "TEXT" (PostgreSQL) – same here
#   {upsert_suffix}  – "OR REPLACE" (SQLite) / "ON CONFLICT" (PostgreSQL)


SCHEMA_TEMPLATE = """\
CREATE TABLE IF NOT EXISTS pages (
    id          {autoincrement},
    path        TEXT NOT NULL UNIQUE,
    title       TEXT NOT NULL DEFAULT '',
    content     TEXT NOT NULL DEFAULT '',
    checksum    TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    updated_at  TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP)
);

CREATE TABLE IF NOT EXISTS entities (
    id          {autoincrement},
    page_id     INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    type        TEXT NOT NULL DEFAULT 'unknown',
    UNIQUE(page_id, name)
);

CREATE TABLE IF NOT EXISTS links (
    id          {autoincrement},
    source_path TEXT NOT NULL,
    target_path TEXT NOT NULL,
    UNIQUE(source_path, target_path)
);

CREATE INDEX IF NOT EXISTS idx_links_source ON links(source_path);
CREATE INDEX IF NOT EXISTS idx_links_target ON links(target_path);
CREATE INDEX IF NOT EXISTS idx_pages_path   ON pages(path);
CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);
"""

SQLITE_FTS_SCHEMA = """\
CREATE VIRTUAL TABLE IF NOT EXISTS fts_pages
USING fts5(path UNINDEXED, title, content, content='pages', content_rowid='id');

CREATE TRIGGER IF NOT EXISTS pages_ai AFTER INSERT ON pages BEGIN
    INSERT INTO fts_pages(rowid, path, title, content)
    VALUES (new.id, new.path, new.title, new.content);
END;

CREATE TRIGGER IF NOT EXISTS pages_ad AFTER DELETE ON pages BEGIN
    INSERT INTO fts_pages(fts_pages, rowid, path, title, content)
    VALUES ('delete', old.id, old.path, old.title, old.content);
END;

CREATE TRIGGER IF NOT EXISTS pages_au AFTER UPDATE ON pages BEGIN
    INSERT INTO fts_pages(fts_pages, rowid, path, title, content)
    VALUES ('delete', old.id, old.path, old.title, old.content);
    INSERT INTO fts_pages(rowid, path, title, content)
    VALUES (new.id, new.path, new.title, new.content);
END;
"""

POSTGRESQL_FTS_SCHEMA = """\
ALTER TABLE pages ADD COLUMN IF NOT EXISTS tsv tsvector
    GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(title, '') || ' ' || coalesce(content, ''))
    ) STORED;

CREATE INDEX IF NOT EXISTS idx_pages_tsv ON pages USING GIN(tsv);
"""


def get_schema_ddl(dialect: str) -> str:
    """Return the full schema DDL for the given *dialect*.

    Args:
        dialect: ``"sqlite"`` or ``"postgresql"``.

    Returns:
        A string of DDL statements separated by ``;``.
    """
    if dialect == "sqlite":
        autoincrement = "INTEGER PRIMARY KEY AUTOINCREMENT"
        base = SCHEMA_TEMPLATE.format(autoincrement=autoincrement)
        return base + "\n" + SQLITE_FTS_SCHEMA
    elif dialect == "postgresql":
        autoincrement = "SERIAL PRIMARY KEY"
        base = SCHEMA_TEMPLATE.format(autoincrement=autoincrement)
        return base + "\n" + POSTGRESQL_FTS_SCHEMA
    else:
        raise ValueError(f"Unknown dialect: {dialect!r}. Expected 'sqlite' or 'postgresql'.")


# ---------------------------------------------------------------------------
# Placeholder normalisation
# ---------------------------------------------------------------------------

def normalise_sql(sql: str, dialect: str) -> str:
    """Convert ``?`` placeholders to the dialect's native style.

    - SQLite expects ``?``.
    - PostgreSQL (psycopg2) expects ``%s``.

    Args:
        sql: SQL statement possibly containing ``?`` placeholders.
        dialect: ``"sqlite"`` or ``"postgresql"``.

    Returns:
        SQL with placeholders normalised for the target dialect.
    """
    if dialect == "postgresql":
        # Replace bare ? with %s, but avoid touching strings / comments.
        return re.sub(r"\?", "%s", sql)
    return sql


# ---------------------------------------------------------------------------
# Markdown helpers (used by sync_page)
# ---------------------------------------------------------------------------

_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+?)(?:[|#][^\]]*)?\]\]")
_MDLINK_RE = re.compile(r"\[(?:[^\]]*)\]\(([^)#?]+?)(?:[#?][^)]*)?\)")
_H1_RE = re.compile(r"^#\s+(.+)", re.MULTILINE)
_FRONTMATTER_TITLE_RE = re.compile(r"^title:\s*(.+)", re.MULTILINE)


def extract_title(content: str, fallback: str = "") -> str:
    """Extract a page title from Markdown *content*.

    Checks YAML frontmatter ``title:`` first, then the first ``# Heading``.

    Args:
        content: Markdown content string.
        fallback: Value to return if no title is found.
    """
    fm_match = _FRONTMATTER_TITLE_RE.search(content[:500])
    if fm_match:
        return fm_match.group(1).strip().strip('"').strip("'")
    h1_match = _H1_RE.search(content)
    if h1_match:
        return h1_match.group(1).strip()
    return fallback


def extract_links(content: str) -> list[str]:
    """Extract all linked page paths from Markdown *content*.

    Handles both ``[[WikiLink]]`` and ``[text](relative/path.md)`` syntax.

    Args:
        content: Markdown content string.

    Returns:
        Deduplicated list of link targets (no anchors, no query strings).
    """
    targets: list[str] = []
    for m in _WIKILINK_RE.finditer(content):
        targets.append(m.group(1).strip())
    for m in _MDLINK_RE.finditer(content):
        href = m.group(1).strip()
        # Skip external links
        if href.startswith("http://") or href.startswith("https://"):
            continue
        targets.append(href)
    # Deduplicate while preserving order
    seen: set[str] = set()
    result: list[str] = []
    for t in targets:
        if t not in seen:
            seen.add(t)
            result.append(t)
    return result


def content_checksum(content: str) -> str:
    """Return a short SHA-256 hex digest of *content*."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
