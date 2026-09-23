import uuid

from app.core.config import get_settings


class StorageService:
    """Handles upload of wardrobe photos / generated look images to cloud storage."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def upload_image(self, file_bytes: bytes, content_type: str) -> str:
        # TODO: upload to S3 / GCS bucket (self.settings.storage_bucket) and return its URL
        key = f"{uuid.uuid4()}"
        raise NotImplementedError(f"Storage backend not configured (would store as {key})")
