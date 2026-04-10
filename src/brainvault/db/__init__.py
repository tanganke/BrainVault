"""Database backend implementations for BrainVault."""

from brainvault.db.sqlite import SQLiteAdapter

__all__ = ["SQLiteAdapter"]

try:
    from brainvault.db.postgresql import PostgreSQLAdapter

    __all__ += ["PostgreSQLAdapter"]
except ImportError:
    pass
