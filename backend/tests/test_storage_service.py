import pytest

from app.core.config import Settings
from app.services.storage import StorageService


def _service_with_settings(monkeypatch, **overrides) -> StorageService:
    # local_storage_dir defaults to unset here regardless of the real .env (which sets
    # it for local dev) — these tests are specifically about the S3 path and the
    # true-unconfigured path, not the local-disk fallback (see test_local_storage_*).
    overrides.setdefault("local_storage_dir", None)
    settings = Settings(**overrides)
    monkeypatch.setattr("app.services.storage.get_settings", lambda: settings)
    return StorageService()


def test_unconfigured_raises_instead_of_returning_a_broken_url(monkeypatch):
    service = _service_with_settings(monkeypatch)

    assert not service.is_configured()
    with pytest.raises(RuntimeError, match="not configured"):
        service.upload_image(b"data", "image/jpeg")


def test_configured_uploads_and_returns_the_s3_url(monkeypatch):
    service = _service_with_settings(
        monkeypatch,
        aws_access_key_id="AKIA...",
        aws_secret_access_key="secret",
        aws_region="eu-west-1",
        storage_bucket="dressme-wardrobe",
    )

    class _FakeClient:
        def __init__(self):
            self.calls = []

        def put_object(self, **kwargs):
            self.calls.append(kwargs)

    fake_client = _FakeClient()
    monkeypatch.setattr("app.services.storage._get_s3_client", lambda: fake_client)

    url = service.upload_image(b"photo-bytes", "image/jpeg")

    assert len(fake_client.calls) == 1
    call = fake_client.calls[0]
    assert call["Bucket"] == "dressme-wardrobe"
    assert call["Body"] == b"photo-bytes"
    assert call["ContentType"] == "image/jpeg"
    assert url == f"https://dressme-wardrobe.s3.eu-west-1.amazonaws.com/{call['Key']}"


def test_custom_endpoint_produces_a_matching_url(monkeypatch):
    service = _service_with_settings(
        monkeypatch,
        aws_access_key_id="key",
        aws_secret_access_key="secret",
        storage_bucket="dressme-wardrobe",
        storage_endpoint_url="https://minio.example.com",
    )
    monkeypatch.setattr("app.services.storage._get_s3_client", lambda: type(
        "C", (), {"put_object": lambda self, **k: None}
    )())

    url = service.upload_image(b"data", "image/jpeg")

    assert url.startswith("https://minio.example.com/dressme-wardrobe/")


def test_local_storage_dir_writes_to_disk_and_returns_a_media_url(tmp_path, monkeypatch):
    service = _service_with_settings(
        monkeypatch,
        local_storage_dir=str(tmp_path),
        public_base_url="http://localhost:8000",
    )

    assert service.is_configured()
    url = service.upload_image(b"photo-bytes", "image/png")

    assert url.startswith("http://localhost:8000/media/")
    assert url.endswith(".png")
    written = list(tmp_path.iterdir())
    assert len(written) == 1
    assert written[0].read_bytes() == b"photo-bytes"
