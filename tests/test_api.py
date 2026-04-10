"""Tests for the BrainVault REST API."""

from __future__ import annotations

import pytest
import yaml
from fastapi.testclient import TestClient

from brainvault.api.app import create_app
from brainvault.api.auth import create_token
from brainvault.api.vault_manager import VaultManager

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def vault_dir(tmp_path):
    """Create a minimal initialised vault directory."""
    (tmp_path / "meta").mkdir()
    cfg_data = {
        "version": "1.1",
        "storage": {"type": "local", "local": {"root_path": str(tmp_path)}},
        "database": {"type": "sqlite", "sqlite": {"file_path": ":memory:"}},
    }
    (tmp_path / "meta" / "config.yaml").write_text(yaml.dump(cfg_data))
    (tmp_path / ".brainvault").mkdir()
    (tmp_path / "wiki").mkdir()
    (tmp_path / "wiki" / "index.md").write_text("# Index\n\nWelcome.\n")
    return tmp_path


@pytest.fixture()
def client(vault_dir):
    """FastAPI test client with one registered vault."""
    app = create_app(vault_dirs={"test-vault": str(vault_dir)})
    with TestClient(app) as c:
        yield c
    app.state.vault_manager.close_all()


@pytest.fixture()
def auth_header():
    """Authorization header with a valid JWT for user 'alice'."""
    token = create_token("alice")
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------


class TestAuth:
    def test_issue_token(self, client):
        resp = client.post("/api/v1/auth/token", json={"user_id": "alice"})
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_issue_token_empty_user_rejected(self, client):
        resp = client.post("/api/v1/auth/token", json={"user_id": ""})
        assert resp.status_code == 422  # validation error

    def test_unauthenticated_request_rejected(self, client):
        resp = client.get("/api/v1/vaults")
        assert resp.status_code in (401, 403)  # missing credentials

    def test_invalid_token_rejected(self, client):
        resp = client.get(
            "/api/v1/vaults",
            headers={"Authorization": "Bearer invalid.jwt.token"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Vault management tests
# ---------------------------------------------------------------------------


class TestVaults:
    def test_list_vaults(self, client, auth_header):
        resp = client.get("/api/v1/vaults", headers=auth_header)
        assert resp.status_code == 200
        vaults = resp.json()
        assert len(vaults) >= 1
        assert any(v["vault_id"] == "test-vault" for v in vaults)

    def test_get_vault(self, client, auth_header):
        resp = client.get("/api/v1/vaults/test-vault", headers=auth_header)
        assert resp.status_code == 200
        data = resp.json()
        assert data["vault_id"] == "test-vault"
        assert data["storage_type"] == "local"
        assert data["db_type"] == "sqlite"

    def test_get_vault_not_found(self, client, auth_header):
        resp = client.get("/api/v1/vaults/nonexistent", headers=auth_header)
        assert resp.status_code == 404

    def test_delete_vault(self, client, auth_header):
        resp = client.delete("/api/v1/vaults/test-vault", headers=auth_header)
        assert resp.status_code == 204
        # Should be gone now
        resp2 = client.get("/api/v1/vaults/test-vault", headers=auth_header)
        assert resp2.status_code == 404

    def test_delete_vault_not_found(self, client, auth_header):
        resp = client.delete("/api/v1/vaults/nonexistent", headers=auth_header)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Vault status tests
# ---------------------------------------------------------------------------


class TestVaultStatus:
    def test_status(self, client, auth_header):
        resp = client.get("/api/v1/vaults/test-vault/status", headers=auth_header)
        assert resp.status_code == 200
        data = resp.json()
        assert data["vault_id"] == "test-vault"
        assert "page_count" in data
        assert "version" in data


# ---------------------------------------------------------------------------
# Page CRUD tests
# ---------------------------------------------------------------------------


class TestPages:
    def test_list_pages(self, client, auth_header):
        resp = client.get("/api/v1/vaults/test-vault/pages", headers=auth_header)
        assert resp.status_code == 200
        pages = resp.json()
        assert any(p["path"] == "wiki/index.md" for p in pages)

    def test_read_page(self, client, auth_header):
        resp = client.get(
            "/api/v1/vaults/test-vault/pages/wiki/index.md",
            headers=auth_header,
        )
        assert resp.status_code == 200
        assert "# Index" in resp.json()["content"]

    def test_read_page_not_found(self, client, auth_header):
        resp = client.get(
            "/api/v1/vaults/test-vault/pages/wiki/nonexistent.md",
            headers=auth_header,
        )
        assert resp.status_code == 404

    def test_write_and_read_page(self, client, auth_header):
        content = "# New Page\n\nHello world.\n"
        resp = client.put(
            "/api/v1/vaults/test-vault/pages/wiki/new.md",
            json={"path": "wiki/new.md", "content": content},
            headers=auth_header,
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # Read it back
        resp2 = client.get(
            "/api/v1/vaults/test-vault/pages/wiki/new.md",
            headers=auth_header,
        )
        assert resp2.status_code == 200
        assert resp2.json()["content"] == content

    def test_delete_page(self, client, auth_header):
        # Create first
        client.put(
            "/api/v1/vaults/test-vault/pages/wiki/deleteme.md",
            json={"path": "wiki/deleteme.md", "content": "# Delete\n"},
            headers=auth_header,
        )
        # Delete
        resp = client.delete(
            "/api/v1/vaults/test-vault/pages/wiki/deleteme.md",
            headers=auth_header,
        )
        assert resp.status_code == 204

        # Should be gone
        resp2 = client.get(
            "/api/v1/vaults/test-vault/pages/wiki/deleteme.md",
            headers=auth_header,
        )
        assert resp2.status_code == 404

    def test_delete_page_not_found(self, client, auth_header):
        resp = client.delete(
            "/api/v1/vaults/test-vault/pages/wiki/ghost.md",
            headers=auth_header,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Search tests
# ---------------------------------------------------------------------------


class TestSearch:
    def test_search_finds_page(self, client, auth_header):
        # Write + sync a page via the API
        client.put(
            "/api/v1/vaults/test-vault/pages/wiki/python.md",
            json={
                "path": "wiki/python.md",
                "content": "# Python\n\nPython is a programming language.\n",
            },
            headers=auth_header,
        )
        resp = client.get(
            "/api/v1/vaults/test-vault/search?q=Python",
            headers=auth_header,
        )
        assert resp.status_code == 200
        results = resp.json()
        assert any(r["path"] == "wiki/python.md" for r in results)

    def test_search_no_results(self, client, auth_header):
        resp = client.get(
            "/api/v1/vaults/test-vault/search?q=xyzzy_nonexistent_term",
            headers=auth_header,
        )
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# Sync tests
# ---------------------------------------------------------------------------


class TestSync:
    def test_sync_vault(self, client, auth_header):
        resp = client.post(
            "/api/v1/vaults/test-vault/sync",
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["synced"] >= 1
        assert data["errors"] == 0


# ---------------------------------------------------------------------------
# VaultManager unit tests
# ---------------------------------------------------------------------------


class TestVaultManager:
    def test_register_and_get(self, vault_dir):
        mgr = VaultManager()
        handle = mgr.register_directory("v1", vault_dir, owner="bob")
        assert handle.vault_id == "v1"
        assert handle.owner == "bob"
        assert mgr.get("v1") is handle
        mgr.close_all()

    def test_duplicate_registration_raises(self, vault_dir):
        mgr = VaultManager()
        mgr.register_directory("v1", vault_dir)
        with pytest.raises(ValueError, match="already registered"):
            mgr.register_directory("v1", vault_dir)
        mgr.close_all()

    def test_list_vaults_by_owner(self, vault_dir):
        mgr = VaultManager()
        mgr.register_directory("v1", vault_dir, owner="alice")
        assert len(mgr.list_vaults(owner="alice")) == 1
        assert len(mgr.list_vaults(owner="bob")) == 0
        mgr.close_all()

    def test_remove_vault(self, vault_dir):
        mgr = VaultManager()
        mgr.register_directory("v1", vault_dir)
        assert mgr.remove("v1") is True
        assert mgr.get("v1") is None
        assert mgr.remove("v1") is False
        mgr.close_all()

    def test_close_all(self, vault_dir):
        mgr = VaultManager()
        mgr.register_directory("v1", vault_dir)
        mgr.close_all()
        assert mgr.get("v1") is None


# ---------------------------------------------------------------------------
# Multi-vault isolation test
# ---------------------------------------------------------------------------


class TestMultiVaultIsolation:
    def test_two_vaults_isolated(self, tmp_path):
        """Pages in vault A should not appear in vault B."""
        # Create two separate vault directories
        vault_a = tmp_path / "vault_a"
        vault_b = tmp_path / "vault_b"
        for v in (vault_a, vault_b):
            (v / "meta").mkdir(parents=True)
            (v / "wiki").mkdir()
            (v / ".brainvault").mkdir()
            cfg = {
                "version": "1.1",
                "storage": {"type": "local", "local": {"root_path": str(v)}},
                "database": {"type": "sqlite", "sqlite": {"file_path": ":memory:"}},
            }
            (v / "meta" / "config.yaml").write_text(yaml.dump(cfg))

        # Write different content to each vault
        (vault_a / "wiki" / "a_only.md").write_text("# Page A\n")
        (vault_b / "wiki" / "b_only.md").write_text("# Page B\n")

        app = create_app(
            vault_dirs={"vault-a": str(vault_a), "vault-b": str(vault_b)},
        )
        token = create_token("tester")
        headers = {"Authorization": f"Bearer {token}"}

        with TestClient(app) as c:
            # Vault A should have a_only.md but not b_only.md
            resp_a = c.get("/api/v1/vaults/vault-a/pages", headers=headers)
            paths_a = {p["path"] for p in resp_a.json()}
            assert "wiki/a_only.md" in paths_a
            assert "wiki/b_only.md" not in paths_a

            # Vault B should have b_only.md but not a_only.md
            resp_b = c.get("/api/v1/vaults/vault-b/pages", headers=headers)
            paths_b = {p["path"] for p in resp_b.json()}
            assert "wiki/b_only.md" in paths_b
            assert "wiki/a_only.md" not in paths_b

        app.state.vault_manager.close_all()
