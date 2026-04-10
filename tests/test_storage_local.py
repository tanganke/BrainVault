"""Tests for LocalStorageAdapter."""

from __future__ import annotations

from pathlib import Path

import pytest


class TestLocalStorageAdapter:
    def test_write_and_read(self, tmp_path):
        from brainvault.storage.local import LocalStorageAdapter

        adapter = LocalStorageAdapter(tmp_path)
        adapter.write("wiki/index.md", "# Index\n")
        assert adapter.read("wiki/index.md") == "# Index\n"

    def test_write_creates_parents(self, tmp_path):
        from brainvault.storage.local import LocalStorageAdapter

        adapter = LocalStorageAdapter(tmp_path)
        adapter.write("wiki/concepts/python.md", "# Python\n")
        assert (tmp_path / "wiki" / "concepts" / "python.md").exists()

    def test_read_missing_raises(self, tmp_path):
        from brainvault.storage.local import LocalStorageAdapter

        adapter = LocalStorageAdapter(tmp_path)
        with pytest.raises(FileNotFoundError):
            adapter.read("missing.md")

    def test_exists_true(self, tmp_path):
        from brainvault.storage.local import LocalStorageAdapter

        adapter = LocalStorageAdapter(tmp_path)
        adapter.write("file.md", "content")
        assert adapter.exists("file.md") is True

    def test_exists_false(self, tmp_path):
        from brainvault.storage.local import LocalStorageAdapter

        adapter = LocalStorageAdapter(tmp_path)
        assert adapter.exists("nope.md") is False

    def test_delete(self, tmp_path):
        from brainvault.storage.local import LocalStorageAdapter

        adapter = LocalStorageAdapter(tmp_path)
        adapter.write("del.md", "bye")
        adapter.delete("del.md")
        assert not adapter.exists("del.md")

    def test_delete_missing_raises(self, tmp_path):
        from brainvault.storage.local import LocalStorageAdapter

        adapter = LocalStorageAdapter(tmp_path)
        with pytest.raises(FileNotFoundError):
            adapter.delete("ghost.md")

    def test_list_all(self, tmp_path):
        from brainvault.storage.local import LocalStorageAdapter

        adapter = LocalStorageAdapter(tmp_path)
        adapter.write("a.md", "")
        adapter.write("wiki/b.md", "")
        adapter.write("wiki/c.md", "")

        paths = set(adapter.list())
        assert "a.md" in paths
        assert "wiki/b.md" in paths
        assert "wiki/c.md" in paths

    def test_list_with_prefix(self, tmp_path):
        from brainvault.storage.local import LocalStorageAdapter

        adapter = LocalStorageAdapter(tmp_path)
        adapter.write("wiki/a.md", "")
        adapter.write("wiki/b.md", "")
        adapter.write("raw/c.txt", "")

        paths = list(adapter.list("wiki/"))
        assert all(p.startswith("wiki/") for p in paths)
        assert "raw/c.txt" not in paths

    def test_list_empty_prefix(self, tmp_path):
        from brainvault.storage.local import LocalStorageAdapter

        adapter = LocalStorageAdapter(tmp_path)
        paths = list(adapter.list())
        assert paths == []

    def test_path_traversal_rejected(self, tmp_path):
        from brainvault.storage.local import LocalStorageAdapter

        adapter = LocalStorageAdapter(tmp_path)
        with pytest.raises(ValueError, match="traversal"):
            adapter._abs("../../../etc/passwd")

    def test_write_and_read_bytes(self, tmp_path):
        from brainvault.storage.local import LocalStorageAdapter

        adapter = LocalStorageAdapter(tmp_path)
        data = b"\x00\x01\x02binary"
        adapter.write_bytes("raw/blob.bin", data)
        assert adapter.read_bytes("raw/blob.bin") == data

    def test_repr(self, tmp_path):
        from brainvault.storage.local import LocalStorageAdapter

        adapter = LocalStorageAdapter(tmp_path)
        assert "LocalStorageAdapter" in repr(adapter)
