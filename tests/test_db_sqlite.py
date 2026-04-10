"""Tests for SQLiteAdapter."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def db():
    """In-memory SQLiteAdapter for fast tests."""
    from brainvault.db.sqlite import SQLiteAdapter

    adapter = SQLiteAdapter(":memory:")
    adapter.initialize()
    yield adapter
    adapter.close()


class TestSQLiteAdapterInit:
    def test_initialize_creates_tables(self, db):
        rows = db.query("SELECT name FROM sqlite_master WHERE type='table'")
        names = {r["name"] for r in rows}
        assert "pages" in names
        assert "entities" in names
        assert "links" in names

    def test_initialize_is_idempotent(self, db):
        db.initialize()  # second call should not raise
        rows = db.query("SELECT name FROM sqlite_master WHERE type='table'")
        assert len(rows) >= 3

    def test_creates_db_file(self, tmp_path):
        from brainvault.db.sqlite import SQLiteAdapter

        db_file = tmp_path / "db" / "test.db"
        adapter = SQLiteAdapter(db_file)
        adapter.initialize()
        assert db_file.exists()
        adapter.close()


class TestSQLiteAdapterCRUD:
    def test_execute_and_query(self, db):
        db.execute(
            "INSERT INTO pages(path, title, content, checksum) VALUES (?,?,?,?)",
            ["wiki/index.md", "Index", "# Index", "abc123"],
        )
        rows = db.query("SELECT path, title FROM pages WHERE path=?", ["wiki/index.md"])
        assert len(rows) == 1
        assert rows[0]["title"] == "Index"

    def test_query_returns_empty_list(self, db):
        rows = db.query("SELECT * FROM pages WHERE path=?", ["nope.md"])
        assert rows == []

    def test_execute_script(self, db):
        db.execute_script(
            "INSERT INTO pages(path, title, content, checksum) VALUES ('a.md','A','','')"
            ";"
            "INSERT INTO pages(path, title, content, checksum) VALUES ('b.md','B','','')"
        )
        rows = db.query("SELECT COUNT(*) AS n FROM pages")
        assert rows[0]["n"] == 2


class TestSQLiteAdapterSyncPage:
    def test_sync_page_inserts(self, db):
        db.set_page_content("# Hello\n\nWorld.")
        db.sync_page("wiki/hello.md")

        rows = db.query("SELECT title FROM pages WHERE path=?", ["wiki/hello.md"])
        assert rows[0]["title"] == "Hello"

    def test_sync_page_updates(self, db):
        db.set_page_content("# Original\n")
        db.sync_page("wiki/page.md")

        db.set_page_content("# Updated\n")
        db.sync_page("wiki/page.md")

        rows = db.query("SELECT title FROM pages WHERE path=?", ["wiki/page.md"])
        assert rows[0]["title"] == "Updated"

    def test_sync_page_skips_unchanged(self, db):
        db.set_page_content("# Same\n")
        db.sync_page("wiki/same.md")

        # Second sync with same content should be a no-op
        db.set_page_content("# Same\n")
        db.sync_page("wiki/same.md")

        rows = db.query("SELECT COUNT(*) AS n FROM pages WHERE path=?", ["wiki/same.md"])
        assert rows[0]["n"] == 1

    def test_sync_page_extracts_links(self, db):
        db.set_page_content("# Page\n\nSee [[other/page]] and [[concepts/ai]].\n")
        db.sync_page("wiki/source.md")

        rows = db.query("SELECT target_path FROM links WHERE source_path=?", ["wiki/source.md"])
        targets = {r["target_path"] for r in rows}
        assert "other/page" in targets
        assert "concepts/ai" in targets

    def test_sync_page_requires_content_staged(self, db):
        with pytest.raises(RuntimeError, match="sync_page requires"):
            db.sync_page("wiki/no-content.md")


class TestSQLiteAdapterSearch:
    def test_search_finds_content(self, db):
        db.set_page_content("# Python Guide\n\nPython is a programming language.")
        db.sync_page("wiki/python.md")

        results = db.search("Python")
        assert len(results) >= 1
        assert any(r["path"] == "wiki/python.md" for r in results)

    def test_search_no_results(self, db):
        results = db.search("xyzzy_not_in_db")
        assert results == []


class TestSQLiteAdapterClose:
    def test_close_and_reopen(self, tmp_path):
        from brainvault.db.sqlite import SQLiteAdapter

        db_file = tmp_path / "test.db"
        adapter = SQLiteAdapter(db_file)
        adapter.initialize()
        adapter.execute(
            "INSERT INTO pages(path,title,content,checksum) VALUES(?,?,?,?)",
            ["p.md", "P", "", "x"],
        )
        adapter.close()

        # Reopen and verify data persists
        adapter2 = SQLiteAdapter(db_file)
        adapter2.initialize()
        rows = adapter2.query("SELECT title FROM pages WHERE path=?", ["p.md"])
        assert rows[0]["title"] == "P"
        adapter2.close()
