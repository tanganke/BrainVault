"""Multi-vault manager for the BrainVault REST API.

The :class:`VaultManager` keeps a registry of vaults.  Each vault is
identified by a ``vault_id`` string and is backed by its own
:class:`~brainvault.core.storage.StorageAdapter` and
:class:`~brainvault.core.database.DatabaseAdapter` pair.

When the API server starts, the manager can be seeded with one or more
vault directories.  Additional vaults can be created at runtime via the
REST API (``POST /api/v1/vaults``).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

from brainvault.config import VaultConfig, load_config
from brainvault.core.database import DatabaseAdapter
from brainvault.core.storage import StorageAdapter
from brainvault.factory import make_database, make_storage


@dataclass
class VaultHandle:
    """In-memory handle for an active vault."""

    vault_id: str
    config: VaultConfig
    storage: StorageAdapter
    db: DatabaseAdapter
    owner: str = ""  # user who created this vault


class VaultManager:
    """Thread-safe registry of active vaults.

    Example::

        mgr = VaultManager()
        mgr.register_directory("my-vault", Path("/data/vaults/my-vault"), owner="alice")
        handle = mgr.get("my-vault")
        pages = handle.storage.list("wiki/")
    """

    def __init__(self) -> None:
        self._vaults: dict[str, VaultHandle] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def register_directory(
        self,
        vault_id: str,
        vault_path: Path,
        owner: str = "",
    ) -> VaultHandle:
        """Load a vault from an on-disk directory and register it.

        Args:
            vault_id: Unique identifier for this vault.
            vault_path: Filesystem path to the vault root (must contain
                ``meta/config.yaml`` or be initialisable).
            owner: User ID of the vault owner.

        Returns:
            The created :class:`VaultHandle`.

        Raises:
            ValueError: If *vault_id* is already registered.
        """
        with self._lock:
            if vault_id in self._vaults:
                raise ValueError(f"Vault {vault_id!r} is already registered")

            cfg = load_config(vault_path)
            storage = make_storage(cfg)
            db = make_database(cfg)
            db.initialize()

            handle = VaultHandle(
                vault_id=vault_id,
                config=cfg,
                storage=storage,
                db=db,
                owner=owner,
            )
            self._vaults[vault_id] = handle
            return handle

    def get(self, vault_id: str) -> VaultHandle | None:
        """Return the :class:`VaultHandle` for *vault_id*, or ``None``."""
        with self._lock:
            return self._vaults.get(vault_id)

    def list_vaults(self, owner: str | None = None) -> list[VaultHandle]:
        """Return all registered vaults, optionally filtered by *owner*."""
        with self._lock:
            handles = list(self._vaults.values())
        if owner is not None:
            handles = [h for h in handles if h.owner == owner]
        return handles

    def remove(self, vault_id: str) -> bool:
        """Unregister and close a vault.  Returns ``True`` if it existed."""
        with self._lock:
            handle = self._vaults.pop(vault_id, None)
        if handle is None:
            return False
        handle.db.close()
        return True

    def close_all(self) -> None:
        """Close every registered vault (used during shutdown)."""
        with self._lock:
            for handle in self._vaults.values():
                handle.db.close()
            self._vaults.clear()
