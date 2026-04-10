"""Abstract database adapter for BrainVault.

All database I/O must go through a :class:`DatabaseAdapter` so that the
higher-level code stays backend-agnostic.  The same SQL (with minor
dialect differences handled inside each adapter) works for both SQLite
and PostgreSQL.

Concrete implementations live in ``brainvault.db``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Sequence


# Type aliases
Row = dict[str, Any]
Params = Sequence[Any] | dict[str, Any]


class DatabaseAdapter(ABC):
    """Abstract interface for all database operations in BrainVault.

    Example usage::

        db.initialize()
        db.execute(
            "INSERT OR REPLACE INTO pages(path, title, content) VALUES (?,?,?)",
            ["wiki/index.md", "Index", "# Index"],
        )
        rows = db.query("SELECT path FROM pages WHERE title=?", ["Index"])
        db.sync_page("wiki/index.md")
        db.close()
    """

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @abstractmethod
    def initialize(self) -> None:
        """Create all tables, indexes, and FTS virtual tables if they do not exist.

        Safe to call multiple times (idempotent).
        """

    @abstractmethod
    def close(self) -> None:
        """Release all connections / return them to the pool."""

    # ------------------------------------------------------------------
    # Core SQL interface
    # ------------------------------------------------------------------

    @abstractmethod
    def execute(self, sql: str, params: Params | None = None) -> None:
        """Execute a SQL statement that does not return rows (INSERT/UPDATE/DELETE/DDL).

        Args:
            sql: SQL statement.  Use ``?`` placeholders for SQLite and
                ``%s`` / ``%(name)s`` for PostgreSQL.  The adapters
                normalise ``?`` → ``%s`` automatically so you may always
                use ``?`` in portable code.
            params: Positional or named bind parameters.
        """

    @abstractmethod
    def query(self, sql: str, params: Params | None = None) -> list[Row]:
        """Execute a SELECT and return all rows as a list of dicts.

        Args:
            sql: SELECT statement (placeholder normalisation applies).
            params: Bind parameters.

        Returns:
            List of :class:`Row` dicts mapping column names → values.
        """

    # ------------------------------------------------------------------
    # High-level helpers
    # ------------------------------------------------------------------

    @abstractmethod
    def sync_page(self, filepath: str) -> None:
        """Synchronise a wiki page into all relevant database tables.

        After a page is written to storage, call this method so the
        adapter updates:
        - the ``pages`` table,
        - the FTS index (``fts_pages``),
        - the ``links`` back-link graph,
        - and – if an embedding model is configured – the ``embeddings``
          table.

        Args:
            filepath: Vault-relative path to the Markdown file
                (e.g. ``wiki/index.md``).
        """

    def execute_script(self, sql: str) -> None:
        """Execute a multi-statement SQL script.

        The default implementation splits on ``;`` and calls
        :meth:`execute` for each non-empty statement.  Subclasses may
        override for more efficient native bulk execution.

        Args:
            sql: One or more SQL statements separated by ``;``.
        """
        for stmt in sql.split(";"):
            stmt = stmt.strip()
            if stmt:
                self.execute(stmt)
