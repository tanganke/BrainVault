"""Tests for S3StorageAdapter using moto."""

from __future__ import annotations

import pytest

boto3 = pytest.importorskip("boto3", reason="boto3 not installed")
moto = pytest.importorskip("moto", reason="moto not installed")

from moto import mock_aws  # noqa: E402


@pytest.fixture()
def s3_adapter():
    """Provide an S3StorageAdapter backed by a moto mock."""
    with mock_aws():
        import boto3 as b3

        client = b3.client(
            "s3",
            region_name="us-east-1",
            aws_access_key_id="test",
            aws_secret_access_key="test",
        )
        client.create_bucket(Bucket="test-vault")

        from brainvault.storage.s3 import S3StorageAdapter

        adapter = S3StorageAdapter(
            bucket="test-vault",
            prefix="brainvault/",
            access_key_id="test",
            secret_access_key="test",
            region="us-east-1",
        )
        yield adapter


class TestS3StorageAdapter:
    def test_write_and_read(self, s3_adapter):
        s3_adapter.write("wiki/index.md", "# Index\n")
        assert s3_adapter.read("wiki/index.md") == "# Index\n"

    def test_read_missing_raises(self, s3_adapter):
        with pytest.raises(FileNotFoundError):
            s3_adapter.read("missing.md")

    def test_exists_true(self, s3_adapter):
        s3_adapter.write("file.md", "content")
        assert s3_adapter.exists("file.md") is True

    def test_exists_false(self, s3_adapter):
        assert s3_adapter.exists("nope.md") is False

    def test_delete(self, s3_adapter):
        s3_adapter.write("del.md", "bye")
        s3_adapter.delete("del.md")
        assert not s3_adapter.exists("del.md")

    def test_delete_missing_raises(self, s3_adapter):
        with pytest.raises(FileNotFoundError):
            s3_adapter.delete("ghost.md")

    def test_list_with_prefix(self, s3_adapter):
        s3_adapter.write("wiki/a.md", "")
        s3_adapter.write("wiki/b.md", "")
        s3_adapter.write("raw/c.txt", "")

        paths = list(s3_adapter.list("wiki/"))
        assert all(p.startswith("wiki/") for p in paths)
        assert len(paths) == 2

    def test_list_all(self, s3_adapter):
        s3_adapter.write("a.md", "")
        s3_adapter.write("b.md", "")
        paths = list(s3_adapter.list())
        assert "a.md" in paths
        assert "b.md" in paths

    def test_write_bytes_and_read_bytes(self, s3_adapter):
        data = b"\x00\x01binary"
        s3_adapter.write_bytes("raw/blob.bin", data)
        assert s3_adapter.read_bytes("raw/blob.bin") == data

    def test_repr(self, s3_adapter):
        assert "S3StorageAdapter" in repr(s3_adapter)
        assert "test-vault" in repr(s3_adapter)

    def test_prefix_stripped_from_list(self, s3_adapter):
        s3_adapter.write("wiki/page.md", "")
        paths = list(s3_adapter.list("wiki/"))
        assert all(not p.startswith("brainvault/") for p in paths)
