"""Download file from MinIO to a temp file."""

import tempfile
from minio import Minio

from worker.config import (
    MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY,
    MINIO_BUCKET, MINIO_USE_SSL,
)

_client: Minio | None = None


def _get_client() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=MINIO_USE_SSL,
        )
    return _client


def download(storage_key: str) -> str:
    """Download file from MinIO → returns temp file path."""
    client = _get_client()
    suffix = "." + storage_key.rsplit(".", 1)[-1] if "." in storage_key else ""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    client.fget_object(MINIO_BUCKET, storage_key, tmp.name)
    tmp.close()
    return tmp.name
