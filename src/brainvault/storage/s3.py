"""S3-compatible storage adapter for BrainVault.

Supports AWS S3, Tencent COS, MinIO, Alibaba OSS, and any other
S3-compatible object storage by accepting a custom *endpoint* URL.

Requires the ``boto3`` package (install with ``pip install brainvault[s3]``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterator

from brainvault.core.storage import StorageAdapter

if TYPE_CHECKING:
    import boto3 as _boto3_t


class S3StorageAdapter(StorageAdapter):
    """Storage adapter backed by S3-compatible object storage.

    Object keys are formed as ``<prefix><path>`` where *prefix* is the
    optional sub-path configured in ``storage.s3.prefix``.

    Args:
        bucket: S3 bucket name.
        prefix: Key prefix (e.g. ``"brainvault/"``).  May be empty.
        access_key_id: AWS / S3-compatible access key ID.
        secret_access_key: AWS / S3-compatible secret access key.
        region: Region name (e.g. ``"us-east-1"``).
        endpoint_url: Custom endpoint for non-AWS providers
            (e.g. ``"https://cos.ap-guangzhou.myqcloud.com"``).
            ``None`` uses the default AWS endpoint.
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        access_key_id: str = "",
        secret_access_key: str = "",
        region: str = "",
        endpoint_url: str | None = None,
    ) -> None:
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "boto3 is required for the S3 storage backend. "
                "Install it with: pip install brainvault[s3]"
            ) from exc

        kwargs: dict = {
            "aws_access_key_id": access_key_id or None,
            "aws_secret_access_key": secret_access_key or None,
            "region_name": region or None,
            "config": Config(signature_version="s3v4"),
        }
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url

        self._s3 = boto3.client("s3", **kwargs)
        self._bucket = bucket
        self._prefix = prefix.rstrip("/") + "/" if prefix else ""

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _key(self, path: str) -> str:
        """Build a full S3 object key from a vault-relative *path*."""
        clean = path.lstrip("/")
        return f"{self._prefix}{clean}"

    def _strip_prefix(self, key: str) -> str:
        """Strip the S3 prefix from a key to get a vault-relative path."""
        if self._prefix and key.startswith(self._prefix):
            return key[len(self._prefix) :]
        return key

    # ------------------------------------------------------------------
    # StorageAdapter interface
    # ------------------------------------------------------------------

    def read(self, path: str) -> str:
        try:
            response = self._s3.get_object(Bucket=self._bucket, Key=self._key(path))
            return response["Body"].read().decode("utf-8")
        except self._s3.exceptions.NoSuchKey:
            raise FileNotFoundError(f"No such object in S3: {path!r}")
        except Exception as exc:
            # Wrap boto3 ClientError with a friendlier message
            if "NoSuchKey" in str(exc) or "404" in str(exc):
                raise FileNotFoundError(f"No such object in S3: {path!r}") from exc
            raise

    def write(self, path: str, content: str) -> None:
        self._s3.put_object(
            Bucket=self._bucket,
            Key=self._key(path),
            Body=content.encode("utf-8"),
            ContentType="text/plain; charset=utf-8",
        )

    def list(self, prefix: str = "") -> Iterator[str]:
        full_prefix = self._key(prefix) if prefix else self._prefix
        paginator = self._s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=full_prefix):
            for obj in page.get("Contents", []):
                yield self._strip_prefix(obj["Key"])

    def delete(self, path: str) -> None:
        key = self._key(path)
        # Check existence first so we can raise FileNotFoundError
        if not self.exists(path):
            raise FileNotFoundError(f"No such object in S3: {path!r}")
        self._s3.delete_object(Bucket=self._bucket, Key=key)

    def exists(self, path: str) -> bool:
        try:
            self._s3.head_object(Bucket=self._bucket, Key=self._key(path))
            return True
        except Exception as exc:
            if "404" in str(exc) or "NoSuchKey" in str(exc) or "Not Found" in str(exc):
                return False
            raise

    def read_bytes(self, path: str) -> bytes:
        try:
            response = self._s3.get_object(Bucket=self._bucket, Key=self._key(path))
            return response["Body"].read()
        except Exception as exc:
            if "NoSuchKey" in str(exc) or "404" in str(exc):
                raise FileNotFoundError(f"No such object in S3: {path!r}") from exc
            raise

    def write_bytes(self, path: str, data: bytes) -> None:
        self._s3.put_object(
            Bucket=self._bucket,
            Key=self._key(path),
            Body=data,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def bucket(self) -> str:
        """The S3 bucket name."""
        return self._bucket

    @property
    def prefix(self) -> str:
        """The S3 key prefix (may be empty)."""
        return self._prefix

    def __repr__(self) -> str:
        return f"S3StorageAdapter(bucket={self._bucket!r}, prefix={self._prefix!r})"
