import json
from collections.abc import Generator
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from cloud_autopkg_runner.cache.azure_blob_cache import AsyncAzureBlobCache, BlobClient
from cloud_autopkg_runner.settings import Settings

if TYPE_CHECKING:
    from cloud_autopkg_runner.metadata_cache import RecipeCache


@pytest_asyncio.fixture
async def azure_cache() -> Generator[AsyncAzureBlobCache, Any, None]:
    """Fixture to create an AsyncS3Cache instance with mocks."""
    with (
        patch.object(Settings, "_instance", None),
        patch.object(AsyncAzureBlobCache, "_instance", None),
    ):
        settings = Settings()
        settings.azure_account_url = "https://testaccount.blob.core.windows.net"
        settings.cloud_container_name = "test-container"
        settings.cache_file = "metadata_cache.json"

        cache = AsyncAzureBlobCache()
        cache._client = AsyncMock(spec=BlobClient)

        yield cache


@pytest.mark.asyncio
async def test_load_cache_invalid_json(
    azure_cache: AsyncAzureBlobCache,
) -> None:
    """Test loading the cache when the JSON is invalid."""
    azure_cache._client.download_blob.return_value = AsyncMock()
    azure_cache._client.download_blob.return_value.readall.return_value = (
        b"invalid json"
    )

    cache_data = await azure_cache.load()

    assert cache_data == {}
    assert azure_cache._is_loaded is True
    azure_cache._client.download_blob.assert_called_once()
    azure_cache._client.download_blob.return_value.readall.assert_called_once()


@pytest.mark.asyncio
async def test_load_cache_skips_if_already_loaded(
    azure_cache: AsyncAzureBlobCache,
) -> None:
    """Test that load() does not call Azure if already loaded."""
    azure_cache._is_loaded = True
    azure_cache._cache_data = {"recipe1": {"timestamp": "test"}}

    with patch.object(azure_cache._client, "download_blob") as mock_download:
        data = await azure_cache.load()
        mock_download.assert_not_called()
        assert data == {"recipe1": {"timestamp": "test"}}


@pytest.mark.asyncio
async def test_save_cache_success(azure_cache: AsyncAzureBlobCache) -> None:
    """Test saving the cache successfully to Azure Blob Storage."""
    azure_cache._cache_data = {"recipe1": {"timestamp": "test"}}

    await azure_cache.save()

    azure_cache._client.upload_blob.assert_called_once_with(
        json.dumps({"recipe1": {"timestamp": "test"}}, indent=4).encode("utf-8"),
        overwrite=True,
    )


@pytest.mark.asyncio
async def test_save_cache_handles_upload_failure(
    azure_cache: AsyncAzureBlobCache,
) -> None:
    """Test that save handles upload failure gracefully."""
    azure_cache._cache_data = {"recipe1": {"timestamp": "test"}}
    azure_cache._is_loaded = True

    with (
        patch.object(
            azure_cache._client, "upload_blob", side_effect=Exception("Upload failed")
        ),
        patch.object(azure_cache._logger, "error") as mock_log,
    ):
        await azure_cache.save()
        mock_log.assert_called_once_with(
            "Error saving metadata to azure://%s/%s",
            "test-container",
            "metadata_cache.json",
            exc_info=True,
        )


@pytest.mark.asyncio
async def test_save_cache_no_double_load(azure_cache: AsyncAzureBlobCache) -> None:
    """Test that save does not trigger load if already loaded."""
    azure_cache._is_loaded = True
    with patch.object(azure_cache, "load", return_value=AsyncMock()) as mock_load:
        await azure_cache.save()
        mock_load.assert_not_called()


@pytest.mark.asyncio
async def test_get_item(azure_cache: AsyncAzureBlobCache) -> None:
    """Test getting an item from the cache."""
    azure_cache._client.download_blob.return_value = AsyncMock()
    azure_cache._client.download_blob.return_value.readall.return_value = json.dumps(
        {"recipe1": {"timestamp": "test"}}
    ).encode("utf-8")

    await azure_cache.load()
    recipe_cache: RecipeCache = {"timestamp": "test"}

    item = await azure_cache.get_item("recipe1")
    assert item == recipe_cache


@pytest.mark.asyncio
async def test_get_item_calls_load_if_not_loaded(
    azure_cache: AsyncAzureBlobCache,
) -> None:
    """Test that get_item() triggers load() if the cache is not loaded."""
    azure_cache._is_loaded = False
    with patch.object(azure_cache, "load", return_value=AsyncMock()) as mock_load:
        await azure_cache.get_item("recipe1")
        mock_load.assert_called_once()


@pytest.mark.asyncio
async def test_get_item_returns_none_if_key_not_found(
    azure_cache: AsyncAzureBlobCache,
) -> None:
    """Test that get_item() returns None if the key is not found."""
    azure_cache._is_loaded = True
    azure_cache._cache_data = {"recipe1": {"timestamp": "test"}}
    item = await azure_cache.get_item("non_existent_key")
    assert item is None


@pytest.mark.asyncio
async def test_set_item(
    azure_cache: AsyncAzureBlobCache,
) -> None:
    """Test setting an item in the cache."""
    recipe_cache: RecipeCache = {"timestamp": "test"}
    await azure_cache.set_item("recipe1", recipe_cache)

    assert "recipe1" in azure_cache._cache_data
    assert azure_cache._cache_data["recipe1"] == recipe_cache


@pytest.mark.asyncio
async def test_delete_item(
    azure_cache: AsyncAzureBlobCache,
) -> None:
    """Test deleting an item from the cache."""
    recipe_cache: RecipeCache = {"timestamp": "test"}
    await azure_cache.set_item("recipe1", recipe_cache)
    assert "recipe1" in azure_cache._cache_data

    await azure_cache.delete_item("recipe1")
    assert "recipe1" not in azure_cache._cache_data


@pytest.mark.asyncio
async def test_delete_non_existent_key(azure_cache: AsyncAzureBlobCache) -> None:
    """Test that delete_item() does not throw if the key does not exist."""
    azure_cache._is_loaded = True
    azure_cache._cache_data = {"recipe1": {"timestamp": "test"}}
    await azure_cache.delete_item("non_existent_key")  # Should not raise an error
    assert "recipe1" in azure_cache._cache_data


@pytest.mark.asyncio
async def test_clear_cache(azure_cache: AsyncAzureBlobCache) -> None:
    """Test clearing the cache."""
    azure_cache._client.download_blob.return_value = AsyncMock()
    azure_cache._client.download_blob.return_value.readall.return_value = json.dumps(
        {"recipe1": {"timestamp": "test"}}
    ).encode("utf-8")

    # Add an item to the cache and check if it's present.
    recipe_cache: RecipeCache = {"timestamp": "test"}
    await azure_cache.set_item("recipe1", recipe_cache)
    assert "recipe1" in azure_cache._cache_data

    # Now clear the cache and check that upload_blob is called correctly.
    await azure_cache.clear_cache()
    assert azure_cache._cache_data == {}

    # Check if the upload_blob was called to save the empty cache.
    azure_cache._client.upload_blob.assert_called_once_with(
        json.dumps({}, indent=4).encode("utf-8"),
        overwrite=True,
    )


@pytest.mark.asyncio
async def test_close(azure_cache: AsyncAzureBlobCache) -> None:
    """Test that `self._client` does not exist after closing."""
    await azure_cache.close()
    assert not hasattr(azure_cache, "_client")
