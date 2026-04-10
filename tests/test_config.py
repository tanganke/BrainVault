"""Tests for brainvault.config."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml


def _write_config(tmp_path: Path, data: dict) -> Path:
    meta = tmp_path / "meta"
    meta.mkdir()
    cfg_path = meta / "config.yaml"
    cfg_path.write_text(yaml.dump(data), encoding="utf-8")
    return tmp_path


class TestLoadConfig:
    def test_defaults_when_no_file(self, tmp_path):
        """load_config() returns sensible defaults if config.yaml is missing."""
        from brainvault.config import load_config

        cfg = load_config(tmp_path)
        assert cfg.version == "1.1"
        assert cfg.storage.type == "local"
        assert cfg.database.type == "sqlite"
        assert cfg.database.sqlite.file_path == "db/brainvault.db"
        assert cfg.database.sqlite.journal_mode == "wal"
        assert cfg.llm.provider == "openclaws"
        assert cfg.mcp.enabled is True

    def test_reads_storage_type(self, tmp_path):
        _write_config(tmp_path, {"storage": {"type": "s3", "s3": {"bucket": "my-vault"}}})
        from brainvault.config import load_config

        cfg = load_config(tmp_path)
        assert cfg.storage.type == "s3"
        assert cfg.storage.s3.bucket == "my-vault"

    def test_reads_database_type(self, tmp_path):
        _write_config(
            tmp_path,
            {
                "database": {
                    "type": "postgresql",
                    "postgresql": {
                        "host": "db.example.com",
                        "port": 5432,
                        "database": "brainvault",
                        "user": "bv",
                        "password": "secret",
                    },
                }
            },
        )
        from brainvault.config import load_config

        cfg = load_config(tmp_path)
        assert cfg.database.type == "postgresql"
        assert cfg.database.postgresql.host == "db.example.com"

    def test_env_var_overrides_db_password(self, tmp_path, monkeypatch):
        _write_config(
            tmp_path,
            {
                "database": {
                    "type": "postgresql",
                    "postgresql": {"password": "from-yaml"},
                }
            },
        )
        monkeypatch.setenv("BRAINVAULT_DB_PASSWORD", "from-env")
        from brainvault.config import load_config

        cfg = load_config(tmp_path)
        assert cfg.database.postgresql.password == "from-env"

    def test_env_var_overrides_s3_keys(self, tmp_path, monkeypatch):
        _write_config(
            tmp_path,
            {
                "storage": {
                    "type": "s3",
                    "s3": {"access_key_id": "yaml-key", "secret_access_key": "yaml-secret"},
                }
            },
        )
        monkeypatch.setenv("BRAINVAULT_S3_ACCESS_KEY", "env-key")
        monkeypatch.setenv("BRAINVAULT_S3_SECRET_KEY", "env-secret")
        from brainvault.config import load_config

        cfg = load_config(tmp_path)
        assert cfg.storage.s3.access_key_id == "env-key"
        assert cfg.storage.s3.secret_access_key == "env-secret"

    def test_vault_root_is_resolved(self, tmp_path):
        from brainvault.config import load_config

        cfg = load_config(tmp_path)
        assert cfg.vault_root == tmp_path.resolve()

    def test_llm_settings(self, tmp_path):
        _write_config(
            tmp_path,
            {"llm": {"provider": "claude", "model": "claude-3-opus", "temperature": 0.5}},
        )
        from brainvault.config import load_config

        cfg = load_config(tmp_path)
        assert cfg.llm.provider == "claude"
        assert cfg.llm.model == "claude-3-opus"
        assert cfg.llm.temperature == 0.5

    def test_auto_lint_settings(self, tmp_path):
        _write_config(
            tmp_path,
            {"auto_lint": {"enabled": False, "cron": "0 0 * * *", "notify": ["slack"]}},
        )
        from brainvault.config import load_config

        cfg = load_config(tmp_path)
        assert cfg.auto_lint.enabled is False
        assert cfg.auto_lint.cron == "0 0 * * *"
        assert cfg.auto_lint.notify == ["slack"]


class TestFindVaultRoot:
    def test_finds_meta_config(self, tmp_path):
        (tmp_path / "meta").mkdir()
        (tmp_path / "meta" / "config.yaml").write_text("version: '1.1'")
        sub = tmp_path / "wiki" / "concepts"
        sub.mkdir(parents=True)

        from brainvault.config import find_vault_root

        found = find_vault_root(sub)
        assert found == tmp_path

    def test_finds_dot_brainvault(self, tmp_path):
        (tmp_path / ".brainvault").mkdir()
        sub = tmp_path / "raw" / "sources"
        sub.mkdir(parents=True)

        from brainvault.config import find_vault_root

        found = find_vault_root(sub)
        assert found == tmp_path

    def test_returns_none_outside_vault(self, tmp_path):
        from brainvault.config import find_vault_root

        assert find_vault_root(tmp_path) is None
