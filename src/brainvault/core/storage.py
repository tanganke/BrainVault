"""Abstract storage adapter for BrainVault.

All file I/O in BrainVault must go through a :class:`StorageAdapter` so that
the higher-level code (LLM compiler, MCP server, CLI) stays backend-agnostic.
Concrete implementations live in ``brainvault.storage``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator


class StorageAdapter(ABC):
    """Abstract interface for reading and writing vault files.

    Paths are always *relative to the vault root* (or the S3 prefix),
    using forward-slash separators regardless of the OS.

    Example usage::

        adapter.write("wiki/index.md", "# Index\\n")
        content = adapter.read("wiki/index.md")
        for path in adapter.list("wiki/"):
            print(path)
        adapter.delete("wiki/orphans/stale.md")
    """

    # ------------------------------------------------------------------
    # Required operations
    # ------------------------------------------------------------------

    @abstractmethod
    def read(self, path: str) -> str:
        """Return the UTF-8 text content of *path*.

        Args:
            path: Vault-relative path (e.g. ``wiki/index.md``).

        Returns:
            File content as a string.

        Raises:
            FileNotFoundError: If the path does not exist.
        """

    @abstractmethod
    def write(self, path: str, content: str) -> None:
        """Write UTF-8 *content* to *path*, creating parent directories as needed.

        Args:
            path: Vault-relative path.
            content: Text content to write.
        """

    @abstractmethod
    def list(self, prefix: str = "") -> Iterator[str]:
        """Yield all vault-relative paths that start with *prefix*.

        Args:
            prefix: Optional path prefix to filter results
                (e.g. ``"wiki/"``).

        Yields:
            Vault-relative paths as strings.
        """

    @abstractmethod
    def delete(self, path: str) -> None:
        """Delete the file at *path*.

        Args:
            path: Vault-relative path.

        Raises:
            FileNotFoundError: If the path does not exist.
        """

    @abstractmethod
    def exists(self, path: str) -> bool:
        """Return ``True`` if *path* exists in the storage backend.

        Args:
            path: Vault-relative path.
        """

    # ------------------------------------------------------------------
    # Optional convenience helpers (concrete default implementations)
    # ------------------------------------------------------------------

    def read_bytes(self, path: str) -> bytes:
        """Return the raw bytes of *path*.

        The default implementation encodes the text returned by :meth:`read`.
        Subclasses may override to avoid the encode/decode round-trip.

        Args:
            path: Vault-relative path.
        """
        return self.read(path).encode("utf-8")

    def write_bytes(self, path: str, data: bytes) -> None:
        """Write raw *data* bytes to *path*.

        The default implementation decodes the bytes as UTF-8 and calls
        :meth:`write`.  Subclasses may override for binary blobs.

        Args:
            path: Vault-relative path.
            data: Raw bytes to write.
        """
        self.write(path, data.decode("utf-8"))
