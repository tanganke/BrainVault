"""Tests for the database schema utilities."""

from __future__ import annotations

from brainvault.db.schema import (
    content_checksum,
    extract_links,
    extract_title,
    get_schema_ddl,
    normalise_sql,
)


class TestGetSchemaDdl:
    def test_sqlite_schema_contains_tables(self):
        ddl = get_schema_ddl("sqlite")
        assert "CREATE TABLE IF NOT EXISTS pages" in ddl
        assert "CREATE TABLE IF NOT EXISTS entities" in ddl
        assert "CREATE TABLE IF NOT EXISTS links" in ddl
        assert "AUTOINCREMENT" in ddl

    def test_sqlite_schema_contains_fts(self):
        ddl = get_schema_ddl("sqlite")
        assert "fts5" in ddl
        assert "fts_pages" in ddl

    def test_postgresql_schema_contains_tables(self):
        ddl = get_schema_ddl("postgresql")
        assert "CREATE TABLE IF NOT EXISTS pages" in ddl
        assert "SERIAL PRIMARY KEY" in ddl

    def test_postgresql_schema_contains_tsvector(self):
        ddl = get_schema_ddl("postgresql")
        assert "tsvector" in ddl or "tsv" in ddl

    def test_unknown_dialect_raises(self):
        import pytest

        with pytest.raises(ValueError, match="Unknown dialect"):
            get_schema_ddl("mysql")


class TestNormaliseSql:
    def test_sqlite_unchanged(self):
        sql = "SELECT * FROM pages WHERE path=?"
        assert normalise_sql(sql, "sqlite") == sql

    def test_postgresql_replaces_question_marks(self):
        sql = "INSERT INTO pages(path, title) VALUES (?,?)"
        result = normalise_sql(sql, "postgresql")
        assert result == "INSERT INTO pages(path, title) VALUES (%s,%s)"

    def test_postgresql_no_placeholders_unchanged(self):
        sql = "SELECT COUNT(*) FROM pages"
        assert normalise_sql(sql, "postgresql") == sql


class TestExtractTitle:
    def test_h1_heading(self):
        assert extract_title("# Hello World\n\nSome text.") == "Hello World"

    def test_frontmatter_title(self):
        content = "---\ntitle: My Page\n---\n# Other\n"
        assert extract_title(content) == "My Page"

    def test_frontmatter_takes_precedence(self):
        content = "---\ntitle: FM Title\n---\n# H1 Title\n"
        assert extract_title(content) == "FM Title"

    def test_fallback(self):
        assert extract_title("no title here", fallback="fallback") == "fallback"

    def test_quoted_frontmatter(self):
        content = '---\ntitle: "Quoted Title"\n---\n'
        assert extract_title(content) == "Quoted Title"


class TestExtractLinks:
    def test_wikilinks(self):
        content = "See [[concepts/python]] and [[entities/guido]]."
        links = extract_links(content)
        assert "concepts/python" in links
        assert "entities/guido" in links

    def test_markdown_links(self):
        content = "See [Python](concepts/python.md) for more."
        links = extract_links(content)
        assert "concepts/python.md" in links

    def test_external_links_excluded(self):
        content = "[Google](https://google.com) and [local](local.md)."
        links = extract_links(content)
        assert "local.md" in links
        assert not any("google" in l for l in links)

    def test_deduplication(self):
        content = "[[page]] and [[page]] again."
        links = extract_links(content)
        assert links.count("page") == 1

    def test_wikilink_with_alias(self):
        content = "[[page/path|Alias Text]]"
        links = extract_links(content)
        assert "page/path" in links

    def test_empty_content(self):
        assert extract_links("") == []


class TestContentChecksum:
    def test_same_content_same_hash(self):
        assert content_checksum("hello") == content_checksum("hello")

    def test_different_content_different_hash(self):
        assert content_checksum("hello") != content_checksum("world")

    def test_returns_16_chars(self):
        assert len(content_checksum("any content")) == 16
