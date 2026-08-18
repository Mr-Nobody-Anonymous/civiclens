"""Storage abstraction. Videos/images are stored under private keys and are
NEVER exposed as public URLs — access goes through authorised API endpoints.

Backends:
  local — files under CL_STORAGE_DIR (default)
  s3    — any S3-compatible object store (boto3 required, credentials via env)
"""
import os
import shutil
import uuid
from abc import ABC, abstractmethod
from typing import BinaryIO

from .config import settings


class StorageBackend(ABC):
    @abstractmethod
    def save(self, key: str, stream: BinaryIO) -> int: ...
    @abstractmethod
    def open(self, key: str) -> BinaryIO: ...
    @abstractmethod
    def path(self, key: str) -> str: ...
    @abstractmethod
    def delete(self, key: str) -> None: ...
    @abstractmethod
    def exists(self, key: str) -> bool: ...


class LocalStorage(StorageBackend):
    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        os.makedirs(self.root, exist_ok=True)

    def _full(self, key: str) -> str:
        p = os.path.abspath(os.path.join(self.root, key))
        if not p.startswith(self.root):
            raise ValueError("invalid storage key")
        return p

    def save(self, key: str, stream: BinaryIO) -> int:
        p = self._full(key)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            shutil.copyfileobj(stream, f)
        return os.path.getsize(p)

    def open(self, key: str):
        return open(self._full(key), "rb")

    def path(self, key: str) -> str:
        return self._full(key)

    def delete(self, key: str):
        p = self._full(key)
        if os.path.exists(p):
            os.remove(p)

    def exists(self, key: str) -> bool:
        return os.path.exists(self._full(key))


class S3Storage(StorageBackend):
    """S3-compatible backend. Credentials come from env vars — never hardcoded."""
    def __init__(self):
        import boto3  # optional dependency
        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3", endpoint_url=settings.s3_endpoint or None,
            aws_access_key_id=settings.s3_access_key or None,
            aws_secret_access_key=settings.s3_secret_key or None,
        )
        self._tmp = os.path.join(settings.storage_dir, "_s3cache")
        os.makedirs(self._tmp, exist_ok=True)

    def save(self, key, stream):
        self.client.upload_fileobj(stream, self.bucket, key)
        head = self.client.head_object(Bucket=self.bucket, Key=key)
        return head["ContentLength"]

    def open(self, key):
        obj = self.client.get_object(Bucket=self.bucket, Key=key)
        return obj["Body"]

    def path(self, key):
        local = os.path.join(self._tmp, key.replace("/", "_"))
        if not os.path.exists(local):
            self.client.download_file(self.bucket, key, local)
        return local

    def delete(self, key):
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def exists(self, key):
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False


def get_storage() -> StorageBackend:
    if settings.storage_backend == "s3":
        return S3Storage()
    return LocalStorage(settings.storage_dir)


storage = get_storage()


def new_key(report_id: str, kind: str, ext: str) -> str:
    return f"reports/{report_id}/{kind}-{uuid.uuid4().hex}{ext}"
