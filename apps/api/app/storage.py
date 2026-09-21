"""MinIO storage helper — upload, download, presign, delete."""

from io import BytesIO

from minio import Minio

from app.config import settings

_client: Minio | None = None


def _get_client() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_USE_SSL,
        )
    return _client


def make_storage_key(
    workspace_id: str, dataset_id: str, document_id: str, filename: str
) -> str:
    return f"workspaces/{workspace_id}/datasets/{dataset_id}/documents/{document_id}/{filename}"


def upload_file(
    storage_key: str,
    data: bytes,
    content_type: str,
) -> str:
    """Upload bytes to MinIO. Returns the storage key."""
    client = _get_client()
    client.put_object(
        settings.MINIO_BUCKET,
        storage_key,
        BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    return storage_key


def get_presigned_url(storage_key: str, expires: int = 3600) -> str:
    """Return a presigned GET URL for the object."""
    from datetime import timedelta
    client = _get_client()
    return client.presigned_get_object(
        settings.MINIO_BUCKET,
        storage_key,
        expires=timedelta(seconds=expires),
    )


def download_file(storage_key: str) -> bytes:
    """Read a whole object into memory (small files only — logos)."""
    client = _get_client()
    resp = client.get_object(settings.MINIO_BUCKET, storage_key)
    try:
        return resp.read()
    finally:
        resp.close()
        resp.release_conn()


def delete_file(storage_key: str) -> None:
    """Delete an object from MinIO."""
    client = _get_client()
    client.remove_object(settings.MINIO_BUCKET, storage_key)
