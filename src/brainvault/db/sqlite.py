"""SQLite database adapter for BrainVault.

Uses the standard-library ``sqlite3`` module with WAL journal mode and
foreign-key enforcement enabled.  The FTS5 virtual table provides fast
full-text search.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Sequence

from brainvault.core.database import DatabaseAdapter, Params, Row
from brainvault.db.schema import (
    content_checksum,
    extract_links,
    extract_title,
    get_schema_ddl,
    normalise_sql,
)


class SQLiteAdapter(DatabaseAdapter):
    """Database adapter backed by SQLite.

    Args:
        file_path: Path to the ``.db`` file.  Parent directories are
            created automatically.  Use ``":memory:"`` for an in-process
            ephemeral database (useful in tests).
        journal_mode: SQLite journal mode.  Defaults to ``"wal"`` for
            better concurrent read performance.
    """

    def __init__(self, file_path: str | Path, journal_mode: str = "wal") -> None:
        self._file_path = str(file_path)
        self._journal_mode = journal_mode
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            if self._file_path != ":memory:":
                Path(self._file_path).parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self._file_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(f"PRAGMA journal_mode = {self._journal_mode.upper()}")
            self._conn = conn
        return self._conn

    # ------------------------------------------------------------------
    # DatabaseAdapter interface
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        conn = self._connect()
        ddl = get_schema_ddl("sqlite")
        conn.executescript(ddl)
        conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def execute(self, sql: str, params: Params | None = None) -> None:
        conn = self._connect()
        sql = normalise_sql(sql, "sqlite")
        if params is None:
            conn.execute(sql)
        else:
            conn.execute(sql, params)
        conn.commit()

    def query(self, sql: str, params: Params | None = None) -> list[Row]:
        conn = self._connect()
        sql = normalise_sql(sql, "sqlite")
        if params is None:
            cur = conn.execute(sql)
        else:
            cur = conn.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]

    def execute_script(self, sql: str) -> None:
        conn = self._connect()
        conn.executescript(sql)
        conn.commit()

    def sync_page(self, filepath: str) -> None:
        """Synchronise *filepath* into the pages, links, and FTS tables.

        If the file content hasn't changed (same checksum) the update is
        skipped to avoid unnecessary I/O.

        Args:
            filepath: Vault-relative path to the Markdown file.
        """
        conn = self._connect()

        # Read current file content via the storage adapter if available,
        # otherwise expect a ``content`` attribute set by the caller.
        # In normal operation the CLI / MCP layer reads the file before
        # calling sync_page.
        content = getattr(self, "_pending_content", None)
        if content is None:
            raise RuntimeError(
                "sync_page requires file content to be set via "
                "SQLiteAdapter.set_page_content(content) before calling sync_page()."
            )
        self._pending_content = None

        title = extract_title(content, fallback=Path(filepath).stem)
        checksum = content_checksum(content)

        # Check if page exists and hasn't changed
        row = conn.execute("SELECT id, checksum FROM pages WHERE path=?", (filepath,)).fetchone()
        if row and row["checksum"] == checksum:
            return  # No change

        if row:
            conn.execute(
                "UPDATE pages SET title=?, content=?, checksum=?, updated_at=CURRENT_TIMESTAMP "
                "WHERE path=?",
                (title, content, checksum, filepath),
            )
        else:
            conn.execute(
                "INSERT INTO pages(path, title, content, checksum) VALUES (?,?,?,?)",
                (filepath, title, content, checksum),
            )

        # Update back-links
        conn.execute("DELETE FROM links WHERE source_path=?", (filepath,))
        for target in extract_links(content):
            conn.execute(
                "INSERT OR IGNORE INTO links(source_path, target_path) VALUES (?,?)",
                (filepath, target),
            )

        conn.commit()

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def set_page_content(self, content: str) -> "SQLiteAdapter":
        """Stage *content* for the next :meth:`sync_page` call.

        This is a simple thread-local workaround that avoids needing to
        pass content through :meth:`sync_page`'s signature (which must
        match the abstract base class).

        Returns:
            ``self`` for chaining.
        """
        self._pending_content = content
        return self

    def search(self, query: str, limit: int = 20) -> list[Row]:
        """Full-text search over pages using FTS5.

        Args:
            query: FTS5 query string (e.g. ``"python AND ai"``).
            limit: Maximum number of results to return.

        Returns:
            List of :class:`Row` dicts with keys: ``path``, ``title``,
            ``rank`` (lower is better).
        """
        sql = (
            "SELECT p.path, p.title, fts.rank "
            "FROM fts_pages fts JOIN pages p ON fts.rowid=p.id "
            "WHERE fts_pages MATCH ? "
            "ORDER BY fts.rank "
            "LIMIT ?"
        )
        return self.query(sql, [query, limit])

    def __repr__(self) -> str:
        return f"SQLiteAdapter(file_path={self._file_path!r})"
