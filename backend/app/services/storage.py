import uuid
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings


class StorageService:
    """Handles upload of wardrobe photos / generated look images to S3-compatible
    cloud storage (real AWS S3, or MinIO/DigitalOcean Spaces/etc. via
    storage_endpoint_url) — or, if local_storage_dir is explicitly set instead, plain
    local disk for dev/testing without any cloud account (served via StaticFiles, see
    app/main.py). No *implicit* fallback when neither is configured — unlike
    Pinecone/the LLM/weather, there's no meaningful "best-effort" degradation for a
    feature whose entire job is producing a URL; callers should check is_configured()
    and fail clearly (see app/api/routes/wardrobe.py) rather than get back a broken
    one.
    """

    def __init__(self) -> None:
        self.settings = get_settings()

    def is_configured(self) -> bool:
        return bool(
            (self.settings.aws_access_key_id and self.settings.aws_secret_access_key)
            or self.settings.local_storage_dir
        )

    def upload_image(self, file_bytes: bytes, content_type: str) -> str:
        if self.settings.local_storage_dir:
            return self._upload_local(file_bytes, content_type)
        if not (self.settings.aws_access_key_id and self.settings.aws_secret_access_key):
            raise RuntimeError("Storage backend not configured (AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY missing)")

        key = f"{uuid.uuid4()}"
        client = _get_s3_client()
        client.put_object(
            Bucket=self.settings.storage_bucket,
            Key=key,
            Body=file_bytes,
            ContentType=content_type,
        )
        return self._public_url(key)

    def _upload_local(self, file_bytes: bytes, content_type: str) -> str:
        extension = "png" if content_type == "image/png" else "jpg"
        key = f"{uuid.uuid4()}.{extension}"
        directory = Path(self.settings.local_storage_dir)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / key).write_bytes(file_bytes)
        return f"{self.settings.public_base_url.rstrip('/')}/media/{key}"

    def _public_url(self, key: str) -> str:
        if self.settings.storage_endpoint_url:
            return f"{self.settings.storage_endpoint_url.rstrip('/')}/{self.settings.storage_bucket}/{key}"
        return f"https://{self.settings.storage_bucket}.s3.{self.settings.aws_region}.amazonaws.com/{key}"


@lru_cache
def _get_s3_client():
    import boto3
    from botocore.config import Config

    settings = get_settings()
    # Non-AWS S3-compatible endpoints (MinIO, DigitalOcean Spaces, ...) generally
    # don't support virtual-hosted-style addressing (bucket.endpoint.tld) since
    # that'd need wildcard DNS for the endpoint — path-style (endpoint.tld/bucket)
    # is what actually works against them.
    client_config = Config(s3={"addressing_style": "path"}) if settings.storage_endpoint_url else None
    return boto3.client(
        "s3",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        endpoint_url=settings.storage_endpoint_url,
        config=client_config,
    )
