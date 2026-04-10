"""Tests for the MCPServer."""

from __future__ import annotations

import json
import socket
import time
from pathlib import Path

import pytest
import yaml


@pytest.fixture()
def vault_with_server(tmp_path):
    """Create an initialised vault and start an MCP server."""
    from brainvault.config import load_config
    from brainvault.factory import make_database, make_storage
    from brainvault.mcp.server import MCPServer

    # Minimal config
    (tmp_path / "meta").mkdir()
    cfg_data = {
        "version": "1.1",
        "storage": {"type": "local", "local": {"root_path": str(tmp_path)}},
        "database": {"type": "sqlite", "sqlite": {"file_path": ":memory:"}},
        "mcp": {"enabled": True, "socket_path": ".brainvault/mcp/test.sock"},
    }
    (tmp_path / "meta" / "config.yaml").write_text(yaml.dump(cfg_data))
    (tmp_path / ".brainvault" / "mcp").mkdir(parents=True)

    cfg = load_config(tmp_path)
    storage = make_storage(cfg)
    db = make_database(cfg)
    db.initialize()

    server = MCPServer(config=cfg, storage=storage, db=db)
    server.start()
    time.sleep(0.1)  # Allow server thread to start

    yield server, storage, db, tmp_path

    server.stop()
    db.close()


def _call(socket_path: str, method: str, params: dict) -> dict:
    """Send one JSON-RPC request to the MCP server and return the response."""
    req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.connect(socket_path)
        s.sendall(req.encode() + b"\n")
        s.settimeout(5)
        buf = b""
        while b"\n" not in buf:
            buf += s.recv(4096)
        return json.loads(buf.split(b"\n")[0])


class TestMCPServer:
    def test_ping(self, vault_with_server):
        server, *_ = vault_with_server
        resp = _call(server.socket_path, "vault.ping", {})
        assert resp["result"]["pong"] is True

    def test_status(self, vault_with_server):
        server, *_ = vault_with_server
        resp = _call(server.socket_path, "vault.status", {})
        assert "storage_type" in resp["result"]
        assert "db_type" in resp["result"]

    def test_storage_write_read(self, vault_with_server):
        server, *_ = vault_with_server
        _call(server.socket_path, "storage.write", {"path": "wiki/test.md", "content": "# Test\n"})
        resp = _call(server.socket_path, "storage.read", {"path": "wiki/test.md"})
        assert resp["result"]["content"] == "# Test\n"

    def test_storage_exists(self, vault_with_server):
        server, *_ = vault_with_server
        _call(server.socket_path, "storage.write", {"path": "wiki/ex.md", "content": ""})
        resp = _call(server.socket_path, "storage.exists", {"path": "wiki/ex.md"})
        assert resp["result"]["exists"] is True

    def test_storage_list(self, vault_with_server):
        server, *_ = vault_with_server
        _call(server.socket_path, "storage.write", {"path": "wiki/a.md", "content": ""})
        _call(server.socket_path, "storage.write", {"path": "wiki/b.md", "content": ""})
        resp = _call(server.socket_path, "storage.list", {"prefix": "wiki/"})
        paths = resp["result"]["paths"]
        assert "wiki/a.md" in paths
        assert "wiki/b.md" in paths

    def test_storage_delete(self, vault_with_server):
        server, *_ = vault_with_server
        _call(server.socket_path, "storage.write", {"path": "wiki/del.md", "content": ""})
        _call(server.socket_path, "storage.delete", {"path": "wiki/del.md"})
        resp = _call(server.socket_path, "storage.exists", {"path": "wiki/del.md"})
        assert resp["result"]["exists"] is False

    def test_db_execute_and_query(self, vault_with_server):
        server, *_ = vault_with_server
        _call(
            server.socket_path,
            "db.execute",
            {
                "sql": "INSERT INTO pages(path,title,content,checksum) VALUES (?,?,?,?)",
                "params": ["wiki/q.md", "Q", "", "abc"],
            },
        )
        resp = _call(
            server.socket_path,
            "db.query",
            {"sql": "SELECT title FROM pages WHERE path=?", "params": ["wiki/q.md"]},
        )
        assert resp["result"]["rows"][0]["title"] == "Q"

    def test_db_sync_page(self, vault_with_server):
        server, *_ = vault_with_server
        resp = _call(
            server.socket_path,
            "db.sync_page",
            {"filepath": "wiki/sync.md", "content": "# Synced\n\nContent."},
        )
        assert resp["result"]["ok"] is True
        # Verify it landed in the DB
        resp2 = _call(
            server.socket_path,
            "db.query",
            {"sql": "SELECT title FROM pages WHERE path=?", "params": ["wiki/sync.md"]},
        )
        assert resp2["result"]["rows"][0]["title"] == "Synced"

    def test_unknown_method_error(self, vault_with_server):
        server, *_ = vault_with_server
        resp = _call(server.socket_path, "unknown.method", {})
        assert "error" in resp

    def test_invalid_json_error(self, vault_with_server):
        server, *_ = vault_with_server
        sock_path = server.socket_path
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.connect(sock_path)
            s.sendall(b"NOT JSON\n")
            s.settimeout(5)
            buf = b""
            while b"\n" not in buf:
                buf += s.recv(4096)
            resp = json.loads(buf.split(b"\n")[0])
        assert resp["error"]["code"] == -32700
