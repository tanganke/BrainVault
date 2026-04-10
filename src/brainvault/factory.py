"""Factory functions for creating storage and database adapters from config.

Usage::

    from brainvault.factory import make_storage, make_database
    from brainvault.config import load_config

    cfg = load_config()
    storage = make_storage(cfg)
    db = make_database(cfg)
    db.initialize()
"""

from __future__ import annotations

from brainvault.config import VaultConfig
from brainvault.core.database import DatabaseAdapter
from brainvault.core.storage import StorageAdapter


def make_storage(config: VaultConfig) -> StorageAdapter:
    """Instantiate and return the storage adapter specified by *config*.

    Args:
        config: A loaded :class:`~brainvault.config.VaultConfig`.

    Returns:
        A concrete :class:`~brainvault.core.storage.StorageAdapter`.

    Raises:
        ValueError: If an unknown storage type is specified.
        ImportError: If the ``s3`` extra is not installed when using the
            S3 backend.
    """
    storage_cfg = config.storage
    if storage_cfg.type == "local":
        from brainvault.storage.local import LocalStorageAdapter

        root = storage_cfg.local.root_path
        if not root or root == ".":
            root = str(config.vault_root)
        return LocalStorageAdapter(root_path=root)

    elif storage_cfg.type == "s3":
        from brainvault.storage.s3 import S3StorageAdapter

        s3 = storage_cfg.s3
        return S3StorageAdapter(
            bucket=s3.bucket,
            prefix=s3.prefix,
            access_key_id=s3.access_key_id,
            secret_access_key=s3.secret_access_key,
            region=s3.region,
            endpoint_url=s3.endpoint or None,
        )

    else:
        raise ValueError(
            f"Unknown storage.type {storage_cfg.type!r}. "
            "Expected 'local' or 's3'."
        )


def make_database(config: VaultConfig) -> DatabaseAdapter:
    """Instantiate and return the database adapter specified by *config*.

    Args:
        config: A loaded :class:`~brainvault.config.VaultConfig`.

    Returns:
        A concrete :class:`~brainvault.core.database.DatabaseAdapter`.

    Raises:
        ValueError: If an unknown database type is specified.
        ImportError: If the ``postgresql`` extra is not installed when
            using the PostgreSQL backend.
    """
    db_cfg = config.database
    if db_cfg.type == "sqlite":
        from brainvault.db.sqlite import SQLiteAdapter

        file_path = db_cfg.sqlite.file_path
        # Resolve relative path against vault root
        from pathlib import Path

        if not Path(file_path).is_absolute():
            file_path = str(config.vault_root / file_path)
        return SQLiteAdapter(
            file_path=file_path,
            journal_mode=db_cfg.sqlite.journal_mode,
        )

    elif db_cfg.type == "postgresql":
        from brainvault.db.postgresql import PostgreSQLAdapter

        pg = db_cfg.postgresql
        return PostgreSQLAdapter(
            host=pg.host,
            port=pg.port,
            database=pg.database,
            user=pg.user,
            password=pg.password,
            ssl_mode=pg.ssl_mode,
            pool_size=pg.pool_size,
        )

    else:
        raise ValueError(
            f"Unknown database.type {db_cfg.type!r}. "
            "Expected 'sqlite' or 'postgresql'."
        )
