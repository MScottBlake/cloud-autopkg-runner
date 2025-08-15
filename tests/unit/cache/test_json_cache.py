import json
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import pytest_asyncio

from cloud_autopkg_runner import Settings
from cloud_autopkg_runner.cache.json_cache import AsyncJsonFileCache


@pytest_asyncio.fixture
async def json_cache(tmp_path: Path) -> Generator[AsyncJsonFileCache, Any, None]:
    """Fixture to create an AsyncJsonFileCache instance with mocks."""
    cache_file = tmp_path / "metadata_cache.json"
    cache_file.write_text(json.dumps({"recipe1": {"timestamp": "test"}}))

    with (
        patch.object(Settings, "_instance", None),
        patch.object(AsyncJsonFileCache, "_instance", None),
    ):
        settings = Settings()
        settings.cache_file = cache_file

        cache = AsyncJsonFileCache()
        yield cache


@pytest.mark.asyncio
async def test_load_cache_success(json_cache: AsyncJsonFileCache) -> None:
    """Test loading the cache successfully."""
    cache_data = await json_cache.load()

    assert cache_data == {"recipe1": {"timestamp": "test"}}
    assert json_cache._is_loaded is True


@pytest.mark.asyncio
async def test_load_cache_missing_file(json_cache: AsyncJsonFileCache) -> None:
    """Test loading the cache when the key does not exist."""
    json_cache._file_path.unlink()

    cache_data = await json_cache.load()

    assert cache_data == {}
    assert json_cache._is_loaded is True


@pytest.mark.asyncio
async def test_load_cache_invalid_json(json_cache: AsyncJsonFileCache) -> None:
    """Test loading the cache when the JSON is invalid."""
    json_cache._file_path.write_text("invalid json")

    cache_data = await json_cache.load()

    assert cache_data == {}
    assert json_cache._is_loaded is True


@pytest.mark.asyncio
async def test_load_cache_skips_read_if_already_loaded(
    json_cache: AsyncJsonFileCache,
) -> None:
    """Test that load() does not read from file if already loaded."""
    await json_cache.load()
    json_cache._file_path.write_text("invalid json")

    with patch(
        "cloud_autopkg_runner.cache.json_cache.Path.read_text"
    ) as mock_read_text:
        data = await json_cache.load()
        assert data == {"recipe1": {"timestamp": "test"}}
        mock_read_text.assert_not_called()


@pytest.mark.asyncio
async def test_save_cache_success(json_cache: AsyncJsonFileCache) -> None:
    """Test saving the cache successfully."""
    json_cache._cache_data = {"recipe1": {"timestamp": "test"}}
    json_cache._is_loaded = True
    json_cache._file_path.unlink()

    await json_cache.save()

    file_data = json_cache._file_path.read_text()
    assert file_data == json.dumps({"recipe1": {"timestamp": "test"}}, indent=4)


@pytest.mark.asyncio
async def test_save_cache_handles_failure(json_cache: AsyncJsonFileCache) -> None:
    """Test that save handles failure gracefully."""
    with (
        patch(
            "cloud_autopkg_runner.cache.json_cache.Path.write_text",
            side_effect=Exception,
        ),
        patch.object(json_cache._logger, "exception") as mock_log,
    ):
        await json_cache.save()
        mock_log.assert_called_once_with(
            "Error saving metadata to %s", json_cache._file_path
        )


@pytest.mark.asyncio
async def test_clear_cache(json_cache: AsyncJsonFileCache) -> None:
    """Test clearing the cache."""
    json_cache._cache_data = {"recipe1": {"timestamp": "test"}}
    json_cache._is_loaded = True

    with patch(
        "cloud_autopkg_runner.cache.json_cache.Path.write_text"
    ) as mock_write_text:
        await json_cache.clear_cache()

        assert json_cache._cache_data == {}
        mock_write_text.assert_called_once_with(json.dumps({}, indent=4))


@pytest.mark.asyncio
async def test_get_item(json_cache: AsyncJsonFileCache) -> None:
    """Test getting an item from the cache."""
    await json_cache.load()
    item = await json_cache.get_item("recipe1")
    assert item == {"timestamp": "test"}


@pytest.mark.asyncio
async def test_get_item_calls_load_if_not_loaded(
    json_cache: AsyncJsonFileCache,
) -> None:
    """Test that get_item() triggers load() if the cache is not loaded."""
    json_cache._is_loaded = False
    with patch.object(json_cache, "load") as mock_load:
        await json_cache.get_item("recipe1")
        mock_load.assert_called_once()


@pytest.mark.asyncio
async def test_get_item_returns_none_if_key_not_found(
    json_cache: AsyncJsonFileCache,
) -> None:
    """Test that get_item() returns None if the key is not found."""
    json_cache._is_loaded = True
    json_cache._cache_data = {"recipe1": {"timestamp": "test"}}
    item = await json_cache.get_item("non_existent_key")
    assert item is None


@pytest.mark.asyncio
async def test_set_item(json_cache: AsyncJsonFileCache) -> None:
    """Test setting an item in the cache."""
    await json_cache.load()
    await json_cache.set_item("recipe1", {"timestamp": "test"})

    assert "recipe1" in json_cache._cache_data
    assert json_cache._cache_data["recipe1"] == {"timestamp": "test"}


@pytest.mark.asyncio
async def test_delete_item(json_cache: AsyncJsonFileCache) -> None:
    """Test deleting an item from the cache."""
    await json_cache.load()
    await json_cache.set_item("recipe1", {"timestamp": "test"})
    assert "recipe1" in json_cache._cache_data

    await json_cache.delete_item("recipe1")
    assert "recipe1" not in json_cache._cache_data


@pytest.mark.asyncio
async def test_delete_non_existent_key(json_cache: AsyncJsonFileCache) -> None:
    """Test that delete_item() does not throw if the key does not exist."""
    json_cache._is_loaded = True
    json_cache._cache_data = {"recipe1": {"timestamp": "test"}}
    await json_cache.delete_item("non_existent_key")  # Should not raise an error
    assert "recipe1" in json_cache._cache_data
