"""Storage backend implementations for BrainVault."""

from brainvault.storage.local import LocalStorageAdapter

__all__ = ["LocalStorageAdapter"]

try:
    from brainvault.storage.s3 import S3StorageAdapter

    __all__ += ["S3StorageAdapter"]
except ImportError:
    pass
