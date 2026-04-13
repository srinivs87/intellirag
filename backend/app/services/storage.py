import io
from minio import Minio
from minio.error import S3Error
from app.core.config import settings

_client = None


def get_minio() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        try:
            if not _client.bucket_exists(settings.MINIO_BUCKET):
                _client.make_bucket(settings.MINIO_BUCKET)
                print(f"[MinIO] Created bucket: {settings.MINIO_BUCKET}")
            else:
                print(f"[MinIO] Bucket exists: {settings.MINIO_BUCKET}")
        except S3Error as e:
            print(f"[MinIO] Warning: {e}")
    return _client


async def upload_to_minio(file_bytes: bytes, object_key: str, filename: str) -> str:
    try:
        client = get_minio()
        client.put_object(
            settings.MINIO_BUCKET,
            object_key,
            io.BytesIO(file_bytes),
            length=len(file_bytes),
            content_type=_guess_content_type(filename),
        )
        return object_key
    except Exception as e:
        print(f"[MinIO] Upload warning (continuing): {e}")
        return object_key


async def download_from_minio(object_key: str) -> bytes:
    client = get_minio()
    response = client.get_object(settings.MINIO_BUCKET, object_key)
    return response.read()


def _guess_content_type(filename: str) -> str:
    ext = filename.lower().split(".")[-1]
    types = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "txt": "text/plain",
        "md": "text/markdown",
    }
    return types.get(ext, "application/octet-stream")
