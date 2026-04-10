"""PostgreSQL database adapter for BrainVault.

Uses ``psycopg2`` with a simple connection pool.  Requires
``pip install brainvault[postgresql]``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from brainvault.core.database import DatabaseAdapter, Params, Row
from brainvault.db.schema import (
    content_checksum,
    extract_links,
    extract_title,
    get_schema_ddl,
    normalise_sql,
)


class PostgreSQLAdapter(DatabaseAdapter):
    """Database adapter backed by PostgreSQL.

    A :class:`psycopg2.pool.ThreadedConnectionPool` is used to allow safe
    concurrent access from multiple threads (e.g. an async MCP server).

    Args:
        host: PostgreSQL server hostname.
        port: PostgreSQL server port (default 5432).
        database: Database name.
        user: Database user.
        password: Database password.  In production supply via the
            ``BRAINVAULT_DB_PASSWORD`` environment variable instead.
        ssl_mode: psycopg2 ``sslmode`` parameter (e.g. ``"require"``).
        pool_size: Maximum number of pooled connections.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "brainvault",
        user: str = "brainvault_user",
        password: str = "",
        ssl_mode: str = "prefer",
        pool_size: int = 5,
    ) -> None:
        try:
            import psycopg2
            import psycopg2.extras
            from psycopg2.pool import ThreadedConnectionPool
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "psycopg2 is required for the PostgreSQL backend. "
                "Install it with: pip install brainvault[postgresql]"
            ) from exc

        self._psycopg2 = psycopg2
        self._extras = psycopg2.extras

        dsn = (
            f"host={host} port={port} dbname={database} "
            f"user={user} password={password} sslmode={ssl_mode}"
        )
        self._pool = ThreadedConnectionPool(minconn=1, maxconn=pool_size, dsn=dsn)

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    def _get_conn(self):
        return self._pool.getconn()

    def _put_conn(self, conn, close: bool = False) -> None:
        self._pool.putconn(conn, close=close)

    # ------------------------------------------------------------------
    # DatabaseAdapter interface
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        ddl = get_schema_ddl("postgresql")
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                # executescript equivalent for psycopg2
                for stmt in ddl.split(";"):
                    stmt = stmt.strip()
                    if stmt:
                        cur.execute(stmt)
            conn.commit()
        finally:
            self._put_conn(conn)

    def close(self) -> None:
        if self._pool:
            self._pool.closeall()

    def execute(self, sql: str, params: Params | None = None) -> None:
        sql = normalise_sql(sql, "postgresql")
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._put_conn(conn)

    def query(self, sql: str, params: Params | None = None) -> list[Row]:
        sql = normalise_sql(sql, "postgresql")
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=self._extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                return [dict(row) for row in cur.fetchall()]
        finally:
            self._put_conn(conn)

    def sync_page(self, filepath: str) -> None:
        """Synchronise *filepath* into the pages and links tables.

        See :meth:`~brainvault.db.sqlite.SQLiteAdapter.sync_page` for
        details on how to stage content before calling this method.
        """
        content = getattr(self, "_pending_content", None)
        if content is None:
            raise RuntimeError(
                "sync_page requires content staged via set_page_content() first."
            )
        self._pending_content = None

        title = extract_title(content, fallback=Path(filepath).stem)
        checksum = content_checksum(content)

        rows = self.query("SELECT id, checksum FROM pages WHERE path=%s", (filepath,))
        if rows and rows[0]["checksum"] == checksum:
            return  # No change

        if rows:
            self.execute(
                "UPDATE pages SET title=%s, content=%s, checksum=%s, "
                "updated_at=CURRENT_TIMESTAMP WHERE path=%s",
                (title, content, checksum, filepath),
            )
        else:
            self.execute(
                "INSERT INTO pages(path, title, content, checksum) VALUES (%s,%s,%s,%s)",
                (filepath, title, content, checksum),
            )

        self.execute("DELETE FROM links WHERE source_path=%s", (filepath,))
        for target in extract_links(content):
            self.execute(
                "INSERT INTO links(source_path, target_path) "
                "VALUES (%s,%s) ON CONFLICT DO NOTHING",
                (filepath, target),
            )

    def set_page_content(self, content: str) -> "PostgreSQLAdapter":
        """Stage *content* for the next :meth:`sync_page` call."""
        self._pending_content = content
        return self

    def search(self, query: str, limit: int = 20) -> list[Row]:
        """Full-text search over pages using PostgreSQL ``tsvector``.

        Args:
            query: Plain-text query string.
            limit: Maximum results to return.
        """
        sql = (
            "SELECT path, title, "
            "ts_rank(tsv, plainto_tsquery('english', %s)) AS rank "
            "FROM pages WHERE tsv @@ plainto_tsquery('english', %s) "
            "ORDER BY rank DESC LIMIT %s"
        )
        return self.query(sql, (query, query, limit))

    def __repr__(self) -> str:
        return "PostgreSQLAdapter(...)"
