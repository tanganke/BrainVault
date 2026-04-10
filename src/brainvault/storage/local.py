"""Local filesystem storage adapter for BrainVault."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from brainvault.core.storage import StorageAdapter


class LocalStorageAdapter(StorageAdapter):
    """Storage adapter backed by the local filesystem.

    All vault-relative paths are resolved against *root_path*.

    Args:
        root_path: Absolute path to the vault root (or a sub-directory
            acting as the storage root as configured by
            ``storage.local.root_path`` in ``meta/config.yaml``).
    """

    def __init__(self, root_path: str | Path) -> None:
        self._root = Path(root_path).resolve()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _abs(self, path: str) -> Path:
        """Resolve a vault-relative *path* to an absolute filesystem path.

        Leading slashes and ``..`` traversal are stripped to prevent
        path-traversal attacks.
        """
        # Normalise to a relative path and resolve under root
        rel = Path(path.lstrip("/"))
        resolved = (self._root / rel).resolve()
        # Security: ensure the result is still inside root
        if not str(resolved).startswith(str(self._root)):
            raise ValueError(f"Path traversal detected: {path!r}")
        return resolved

    # ------------------------------------------------------------------
    # StorageAdapter interface
    # ------------------------------------------------------------------

    def read(self, path: str) -> str:
        abs_path = self._abs(path)
        if not abs_path.exists():
            raise FileNotFoundError(f"No such file in vault: {path!r}")
        return abs_path.read_text(encoding="utf-8")

    def write(self, path: str, content: str) -> None:
        abs_path = self._abs(path)
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_text(content, encoding="utf-8")

    def list(self, prefix: str = "") -> Iterator[str]:
        if prefix:
            base = self._abs(prefix)
        else:
            base = self._root

        if not base.exists():
            return

        if base.is_file():
            yield prefix
            return

        for item in sorted(base.rglob("*")):
            if item.is_file():
                yield str(item.relative_to(self._root)).replace("\\", "/")

    def delete(self, path: str) -> None:
        abs_path = self._abs(path)
        if not abs_path.exists():
            raise FileNotFoundError(f"No such file in vault: {path!r}")
        abs_path.unlink()

    def exists(self, path: str) -> bool:
        try:
            return self._abs(path).exists()
        except ValueError:
            return False

    def read_bytes(self, path: str) -> bytes:
        abs_path = self._abs(path)
        if not abs_path.exists():
            raise FileNotFoundError(f"No such file in vault: {path!r}")
        return abs_path.read_bytes()

    def write_bytes(self, path: str, data: bytes) -> None:
        abs_path = self._abs(path)
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_bytes(data)

    # ------------------------------------------------------------------
    # Extra helpers
    # ------------------------------------------------------------------

    @property
    def root(self) -> Path:
        """The resolved filesystem root of this adapter."""
        return self._root

    def __repr__(self) -> str:
        return f"LocalStorageAdapter(root={self._root!r})"
