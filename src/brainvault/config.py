"""BrainVault configuration loader.

Reads ``meta/config.yaml`` relative to the vault root and exposes a typed
:class:`VaultConfig` dataclass.  Sensitive values (passwords, secret keys)
may be supplied via environment variables; the loader resolves them
transparently so they are never hard-coded in YAML.

Environment variable overrides (all optional):
    BRAINVAULT_DB_PASSWORD      – overrides ``database.postgresql.password``
    BRAINVAULT_S3_ACCESS_KEY    – overrides ``storage.s3.access_key_id``
    BRAINVAULT_S3_SECRET_KEY    – overrides ``storage.s3.secret_access_key``
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

import yaml


# ---------------------------------------------------------------------------
# Sub-configs
# ---------------------------------------------------------------------------


@dataclass
class LocalStorageConfig:
    root_path: str = "."


@dataclass
class S3StorageConfig:
    endpoint: str = ""
    bucket: str = ""
    prefix: str = ""
    access_key_id: str = ""
    secret_access_key: str = ""
    region: str = ""


@dataclass
class StorageConfig:
    type: Literal["local", "s3"] = "local"
    local: LocalStorageConfig = field(default_factory=LocalStorageConfig)
    s3: S3StorageConfig = field(default_factory=S3StorageConfig)


@dataclass
class SQLiteConfig:
    file_path: str = "db/brainvault.db"
    journal_mode: str = "wal"


@dataclass
class PostgreSQLConfig:
    host: str = "localhost"
    port: int = 5432
    database: str = "brainvault"
    user: str = "brainvault_user"
    password: str = ""
    ssl_mode: str = "prefer"
    pool_size: int = 5


@dataclass
class DatabaseConfig:
    type: Literal["sqlite", "postgresql"] = "sqlite"
    sqlite: SQLiteConfig = field(default_factory=SQLiteConfig)
    postgresql: PostgreSQLConfig = field(default_factory=PostgreSQLConfig)


@dataclass
class LLMConfig:
    provider: str = "openclaws"
    model: str = "claude-3.7-sonnet"
    temperature: float = 0.3


@dataclass
class MCPConfig:
    enabled: bool = True
    socket_path: str = ".brainvault/mcp/brainvault.sock"


@dataclass
class AutoLintConfig:
    enabled: bool = True
    cron: str = "0 3 * * 0"
    notify: list[str] = field(default_factory=lambda: ["email", "webhook"])


@dataclass
class VaultConfig:
    version: str = "1.1"
    storage: StorageConfig = field(default_factory=StorageConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    mcp: MCPConfig = field(default_factory=MCPConfig)
    auto_lint: AutoLintConfig = field(default_factory=AutoLintConfig)

    # The vault root directory (set at load time, not from YAML)
    vault_root: Path = field(default_factory=Path.cwd, compare=False)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def _merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base* (returns new dict)."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def _parse_storage(raw: dict) -> StorageConfig:
    local_raw = raw.get("local", {})
    s3_raw = raw.get("s3", {})
    return StorageConfig(
        type=raw.get("type", "local"),
        local=LocalStorageConfig(**{k: v for k, v in local_raw.items() if k in LocalStorageConfig.__dataclass_fields__}),
        s3=S3StorageConfig(
            endpoint=s3_raw.get("endpoint", ""),
            bucket=s3_raw.get("bucket", ""),
            prefix=s3_raw.get("prefix", ""),
            access_key_id=os.environ.get("BRAINVAULT_S3_ACCESS_KEY", s3_raw.get("access_key_id", "")),
            secret_access_key=os.environ.get("BRAINVAULT_S3_SECRET_KEY", s3_raw.get("secret_access_key", "")),
            region=s3_raw.get("region", ""),
        ),
    )


def _parse_database(raw: dict) -> DatabaseConfig:
    sqlite_raw = raw.get("sqlite", {})
    pg_raw = raw.get("postgresql", {})
    return DatabaseConfig(
        type=raw.get("type", "sqlite"),
        sqlite=SQLiteConfig(
            file_path=sqlite_raw.get("file_path", "db/brainvault.db"),
            journal_mode=sqlite_raw.get("journal_mode", "wal"),
        ),
        postgresql=PostgreSQLConfig(
            host=pg_raw.get("host", "localhost"),
            port=int(pg_raw.get("port", 5432)),
            database=pg_raw.get("database", "brainvault"),
            user=pg_raw.get("user", "brainvault_user"),
            password=os.environ.get("BRAINVAULT_DB_PASSWORD", pg_raw.get("password", "")),
            ssl_mode=pg_raw.get("ssl_mode", "prefer"),
            pool_size=int(pg_raw.get("pool_size", 5)),
        ),
    )


def load_config(vault_root: Optional[Path] = None) -> VaultConfig:
    """Load and return a :class:`VaultConfig` from *vault_root*/meta/config.yaml.

    If the config file does not exist the function returns a default config
    (useful during ``brainvault init`` before the file is created).

    Args:
        vault_root: Path to the vault root directory.  Defaults to the
            current working directory.

    Returns:
        A fully-populated :class:`VaultConfig` instance.
    """
    if vault_root is None:
        vault_root = Path.cwd()
    vault_root = Path(vault_root).resolve()

    config_path = vault_root / "meta" / "config.yaml"

    raw: dict = {}
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh)
            if isinstance(loaded, dict):
                raw = loaded

    storage_cfg = _parse_storage(raw.get("storage", {}))
    database_cfg = _parse_database(raw.get("database", {}))

    llm_raw = raw.get("llm", {})
    llm_cfg = LLMConfig(
        provider=llm_raw.get("provider", "openclaws"),
        model=llm_raw.get("model", "claude-3.7-sonnet"),
        temperature=float(llm_raw.get("temperature", 0.3)),
    )

    mcp_raw = raw.get("mcp", {})
    mcp_cfg = MCPConfig(
        enabled=bool(mcp_raw.get("enabled", True)),
        socket_path=mcp_raw.get("socket_path", ".brainvault/mcp/brainvault.sock"),
    )

    al_raw = raw.get("auto_lint", {})
    auto_lint_cfg = AutoLintConfig(
        enabled=bool(al_raw.get("enabled", True)),
        cron=al_raw.get("cron", "0 3 * * 0"),
        notify=list(al_raw.get("notify", ["email", "webhook"])),
    )

    return VaultConfig(
        version=str(raw.get("version", "1.1")),
        storage=storage_cfg,
        database=database_cfg,
        llm=llm_cfg,
        mcp=mcp_cfg,
        auto_lint=auto_lint_cfg,
        vault_root=vault_root,
    )


def find_vault_root(start: Optional[Path] = None) -> Optional[Path]:
    """Walk up the directory tree to find the nearest vault root.

    A directory is considered a vault root when it contains a
    ``meta/config.yaml`` **or** a ``.brainvault/`` directory.

    Args:
        start: Directory to start searching from.  Defaults to cwd.

    Returns:
        The vault root :class:`~pathlib.Path`, or ``None`` if not found.
    """
    current = Path(start or Path.cwd()).resolve()
    while True:
        if (current / "meta" / "config.yaml").exists() or (current / ".brainvault").exists():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent
