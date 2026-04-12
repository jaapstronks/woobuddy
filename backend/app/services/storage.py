import io
import logging

from miniopy_async import Minio

from app.config import settings

logger = logging.getLogger(__name__)


class StorageService:
    """Thin wrapper around MinIO for PDF storage."""

    def __init__(self) -> None:
        self._client: Minio | None = None

    @property
    def client(self) -> Minio:
        if self._client is None:
            self._client = Minio(
                endpoint=settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure,
            )
        return self._client

    async def ensure_bucket(self) -> None:
        """Create the documents bucket if it doesn't exist."""
        exists = await self.client.bucket_exists(settings.minio_bucket)
        if not exists:
            await self.client.make_bucket(settings.minio_bucket)
            logger.info("Created MinIO bucket: %s", settings.minio_bucket)

    async def upload(self, key: str, data: bytes, content_type: str = "application/pdf") -> None:
        await self.client.put_object(
            bucket_name=settings.minio_bucket,
            object_name=key,
            data=io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )

    async def download(self, key: str) -> bytes:
        response = await self.client.get_object(
            bucket_name=settings.minio_bucket,
            object_name=key,
        )
        try:
            return await response.read()
        finally:
            response.close()
            await response.release()


storage = StorageService()
