from pathlib import Path
from unittest.mock import MagicMock, patch

from alos.config import Settings
from alos.genesis.uploads import object_storage_is_ready


def test_filesystem_storage_readiness_requires_an_existing_directory(tmp_path: Path) -> None:
    assert object_storage_is_ready(Settings(object_storage_path=tmp_path))
    assert not object_storage_is_ready(Settings(object_storage_path=tmp_path / "missing"))


def test_s3_storage_readiness_uses_a_bucket_head_request() -> None:
    client = MagicMock()
    storage = MagicMock()
    storage._client = client
    settings = Settings(
        object_storage_provider="s3",
        object_storage_bucket="alos-test",
        object_storage_access_key_id="access-key",
        object_storage_secret_access_key="secret-key",
    )

    with patch("alos.genesis.uploads.S3GenesisUploadStorage", return_value=storage):
        assert object_storage_is_ready(settings)

    client.head_bucket.assert_called_once_with(Bucket="alos-test")
