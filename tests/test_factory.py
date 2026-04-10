"""Tests for the factory functions make_storage() and make_database()."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


def _make_vault(tmp_path: Path, storage_type="local", db_type="sqlite") -> Path:
    meta = tmp_path / "meta"
    meta.mkdir(parents=True, exist_ok=True)
    cfg = {
        "version": "1.1",
        "storage": {"type": storage_type, "local": {"root_path": str(tmp_path)}},
        "database": {"type": db_type, "sqlite": {"file_path": ":memory:"}},
    }
    (meta / "config.yaml").write_text(yaml.dump(cfg), encoding="utf-8")
    return tmp_path


class TestMakeStorage:
    def test_local_adapter(self, tmp_path):
        _make_vault(tmp_path, storage_type="local")
        from brainvault.config import load_config
        from brainvault.factory import make_storage
        from brainvault.storage.local import LocalStorageAdapter

        cfg = load_config(tmp_path)
        adapter = make_storage(cfg)
        assert isinstance(adapter, LocalStorageAdapter)

    def test_unknown_storage_type_raises(self, tmp_path):
        from brainvault.config import VaultConfig, StorageConfig
        from brainvault.factory import make_storage

        cfg = VaultConfig(vault_root=tmp_path)
        cfg.storage.type = "ftp"  # type: ignore[assignment]
        with pytest.raises(ValueError, match="Unknown storage.type"):
            make_storage(cfg)


class TestMakeDatabase:
    def test_sqlite_adapter(self, tmp_path):
        _make_vault(tmp_path, db_type="sqlite")
        from brainvault.config import load_config
        from brainvault.db.sqlite import SQLiteAdapter
        from brainvault.factory import make_database

        cfg = load_config(tmp_path)
        adapter = make_database(cfg)
        assert isinstance(adapter, SQLiteAdapter)
        adapter.close()

    def test_unknown_db_type_raises(self, tmp_path):
        from brainvault.config import VaultConfig
        from brainvault.factory import make_database

        cfg = VaultConfig(vault_root=tmp_path)
        cfg.database.type = "mongodb"  # type: ignore[assignment]
        with pytest.raises(ValueError, match="Unknown database.type"):
            make_database(cfg)

    def test_sqlite_file_path_resolved(self, tmp_path):
        """Relative file_path should be resolved against vault_root."""
        _make_vault(tmp_path, db_type="sqlite")
        from brainvault.config import load_config
        from brainvault.factory import make_database

        cfg = load_config(tmp_path)
        cfg.database.sqlite.file_path = "db/brainvault.db"
        adapter = make_database(cfg)
        # The adapter file path should be absolute
        assert Path(adapter._file_path).is_absolute()
        adapter.close()
