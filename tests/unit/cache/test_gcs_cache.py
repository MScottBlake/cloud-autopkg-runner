import json
from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from google.cloud.storage import (  # pyright: ignore[reportMissingTypeStubs]
    Blob,
    Bucket,
    Client,
)

from cloud_autopkg_runner.cache.gcs_cache import AsyncGCSCache
from cloud_autopkg_runner.settings import Settings


@pytest_asyncio.fixture
async def gcs_cache() -> Generator[AsyncGCSCache, Any, None]:
    """Fixture to create an AsyncGCSCache instance with mocks."""
    with (
        patch.object(Settings, "_instance", None),
        patch.object(AsyncGCSCache, "_instance", None),
    ):
        settings = Settings()
        settings.cloud_container_name = "test-container"
        settings.cache_file = "metadata_cache.json"

        cache = AsyncGCSCache()
        cache._client = AsyncMock(spec=Client)
        mock_bucket = MagicMock(spec=Bucket)
        cache._client.bucket.return_value = mock_bucket
        mock_blob = MagicMock(spec=Blob)
        mock_bucket.blob.return_value = mock_blob
        mock_blob.download_as_string = MagicMock(
            return_value=json.dumps({"recipe1": {"timestamp": "test"}}).encode("utf-8")
        )

        yield cache


@pytest.mark.asyncio
async def test_load_cache_success(gcs_cache: AsyncGCSCache) -> None:
    """Test loading the cache successfully from S3."""
    cache_data = await gcs_cache.load()

    assert cache_data == {"recipe1": {"timestamp": "test"}}
    assert gcs_cache._is_loaded is True

    gcs_cache._client.bucket.assert_called_once_with("test-container")
    gcs_cache._client.bucket().blob.assert_called_once_with("metadata_cache.json")
    gcs_cache._client.bucket().blob().download_as_string.assert_called_once()


@pytest.mark.asyncio
async def test_load_cache_invalid_json(gcs_cache: AsyncGCSCache) -> None:
    """Test loading the cache when the JSON is invalid."""
    gcs_cache._client.bucket.return_value = MagicMock(
        read=MagicMock(return_value=b"invalid json")
    )

    cache_data = await gcs_cache.load()

    assert cache_data == {}
    assert gcs_cache._is_loaded is True


@pytest.mark.asyncio
async def test_load_cache_skips_if_already_loaded(gcs_cache: AsyncGCSCache) -> None:
    """Test that load() does not call S3 if already loaded."""
    gcs_cache._is_loaded = True
    gcs_cache._cache_data = {"recipe1": {"timestamp": "test"}}

    data = await gcs_cache.load()
    gcs_cache._client.bucket.assert_not_called()
    assert data == {"recipe1": {"timestamp": "test"}}


@pytest.mark.asyncio
async def test_save_cache_success(gcs_cache: AsyncGCSCache) -> None:
    """Test saving the cache successfully to S3."""
    content = {"recipe1": {"timestamp": "test"}}
    gcs_cache._cache_data = content

    await gcs_cache.save()

    gcs_cache._client.bucket.assert_called_once_with("test-container")
    gcs_cache._client.bucket().blob.assert_called_once_with("metadata_cache.json")
    gcs_cache._client.bucket().blob().upload_from_string.assert_called_once_with(
        json.dumps(content, indent=4).encode("utf-8"), "application/json"
    )


@pytest.mark.asyncio
async def test_save_cache_handles_upload_failure(gcs_cache: AsyncGCSCache) -> None:
    """Test that save handles upload failure gracefully."""
    with (
        patch.object(
            gcs_cache._client.bucket().blob(),
            "upload_from_string",
            side_effect=Exception("Upload failed"),
        ),
        patch.object(gcs_cache._logger, "exception") as mock_log,
    ):
        await gcs_cache.save()
        mock_log.assert_called_once_with(
            "Error saving metadata to gcs://%s/%s",
            "test-container",
            "metadata_cache.json",
        )


@pytest.mark.asyncio
async def test_clear_cache(gcs_cache: AsyncGCSCache) -> None:
    """Test clearing the cache."""
    await gcs_cache.clear_cache()

    assert gcs_cache._cache_data == {}
    gcs_cache._client.bucket().blob().upload_from_string.assert_called_once_with(
        b"{}", "application/json"
    )


@pytest.mark.asyncio
async def test_get_item(gcs_cache: AsyncGCSCache) -> None:
    """Test getting an item from the cache."""
    item = await gcs_cache.get_item("recipe1")
    assert item == {"timestamp": "test"}


@pytest.mark.asyncio
async def test_get_item_calls_load_if_not_loaded(gcs_cache: AsyncGCSCache) -> None:
    """Test that get_item() triggers load() if the cache is not loaded."""
    gcs_cache._is_loaded = False
    with patch.object(gcs_cache, "load") as mock_load:
        await gcs_cache.get_item("recipe1")
        mock_load.assert_called_once()


@pytest.mark.asyncio
async def test_get_item_returns_none_if_key_not_found(gcs_cache: AsyncGCSCache) -> None:
    """Test that get_item() returns None if the key is not found."""
    gcs_cache._is_loaded = True
    gcs_cache._cache_data = {"recipe1": {"timestamp": "test"}}
    item = await gcs_cache.get_item("non_existent_key")
    assert item is None


@pytest.mark.asyncio
async def test_set_item(gcs_cache: AsyncGCSCache) -> None:
    """Test setting an item in the cache."""
    await gcs_cache.load()
    await gcs_cache.set_item("recipe1", {"timestamp": "test"})

    assert "recipe1" in gcs_cache._cache_data
    assert gcs_cache._cache_data["recipe1"] == {"timestamp": "test"}


@pytest.mark.asyncio
async def test_delete_item(gcs_cache: AsyncGCSCache) -> None:
    """Test deleting an item from the cache."""
    await gcs_cache.load()
    await gcs_cache.set_item("recipe1", {"timestamp": "test"})
    assert "recipe1" in gcs_cache._cache_data

    await gcs_cache.delete_item("recipe1")
    assert "recipe1" not in gcs_cache._cache_data


@pytest.mark.asyncio
async def test_delete_non_existent_key(gcs_cache: AsyncGCSCache) -> None:
    """Test that delete_item() does not throw if the key does not exist."""
    gcs_cache._is_loaded = True
    gcs_cache._cache_data = {"recipe1": {"timestamp": "test"}}
    await gcs_cache.delete_item("non_existent_key")  # Should not raise an error
    assert "recipe1" in gcs_cache._cache_data


@pytest.mark.asyncio
async def test_close(gcs_cache: AsyncGCSCache) -> None:
    """Test that `self._client` does not exist after closing."""
    await gcs_cache.close()
    assert not hasattr(gcs_cache, "_client")
