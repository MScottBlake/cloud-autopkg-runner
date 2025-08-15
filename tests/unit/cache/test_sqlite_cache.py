import json
import sqlite3
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from cloud_autopkg_runner import Settings
from cloud_autopkg_runner.cache.sqlite_cache import AsyncSQLiteCache


@pytest_asyncio.fixture
async def sqlite_cache(tmp_path: Path) -> Generator[AsyncSQLiteCache, Any, None]:
    """Fixture to create an AsyncSQLiteCache instance with mocks."""
    cache_file = tmp_path / "metadata_cache.sqlite"

    # Create and pre-populate the SQLite database
    conn = sqlite3.connect(cache_file)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS metadata (
            recipe_name TEXT PRIMARY KEY,
            cache_data TEXT
        )
        """
    )
    cursor.execute(
        "INSERT INTO metadata (recipe_name, cache_data) VALUES (?, ?)",
        ("recipe1", json.dumps({"timestamp": "test"})),
    )
    conn.commit()
    conn.close()

    with (
        patch.object(Settings, "_instance", None),
        patch.object(AsyncSQLiteCache, "_instance", None),
    ):
        settings = Settings()
        settings.cache_file = cache_file

        cache = AsyncSQLiteCache()
        yield cache


@pytest.mark.asyncio
async def test_load_cache_success(sqlite_cache: AsyncSQLiteCache) -> None:
    """Test loading the cache successfully."""
    cache_data = await sqlite_cache.load()

    assert cache_data == {"recipe1": {"timestamp": "test"}}
    assert sqlite_cache._is_loaded is True


@pytest.mark.asyncio
async def test_load_cache_missing_file(sqlite_cache: AsyncSQLiteCache) -> None:
    """Test loading the cache when the key does not exist."""
    sqlite_cache._db_path.unlink()

    cache_data = await sqlite_cache.load()

    assert cache_data == {}
    assert sqlite_cache._is_loaded is True


@pytest.mark.asyncio
async def test_load_cache_invalid_json(sqlite_cache: AsyncSQLiteCache) -> None:
    """Test loading the cache when the JSON is invalid."""
    sqlite_cache._db_path.write_text("invalid json")

    cache_data = await sqlite_cache.load()

    assert cache_data == {}
    assert sqlite_cache._is_loaded is True


@pytest.mark.asyncio
async def test_load_cache_skips_read_if_already_loaded(
    sqlite_cache: AsyncSQLiteCache,
) -> None:
    """Test that load() does not read from file if already loaded."""
    await sqlite_cache.load()
    sqlite_cache._db_path.write_text("invalid json")

    with patch(
        "cloud_autopkg_runner.cache.sqlite_cache.Path.read_text"
    ) as mock_read_text:
        data = await sqlite_cache.load()
        assert data == {"recipe1": {"timestamp": "test"}}
        mock_read_text.assert_not_called()


@pytest.mark.asyncio
async def test_save_cache_success(sqlite_cache: AsyncSQLiteCache) -> None:
    """Test saving the cache successfully."""
    sqlite_cache._cache_data = {"recipe1": {"timestamp": "test"}}
    sqlite_cache._is_loaded = True
    sqlite_cache._db_path.unlink()

    await sqlite_cache.save()

    conn = sqlite3.connect(sqlite_cache._db_path)
    cursor = conn.cursor()

    rows = cursor.execute("SELECT recipe_name, cache_data FROM metadata")
    file_data = {
        recipe_name: json.loads(cache_data) for recipe_name, cache_data in rows
    }

    conn.commit()
    conn.close()

    assert file_data == {"recipe1": {"timestamp": "test"}}


@pytest.mark.asyncio
async def test_save_cache_handles_failure(sqlite_cache: AsyncSQLiteCache) -> None:
    """Test that save handles failure gracefully."""
    sqlite_cache._cache_data = {"test_recipe": {"key": "value"}}

    with (
        patch.object(
            sqlite_cache, "_execute_sql", new=AsyncMock(side_effect=Exception)
        ),
        patch.object(sqlite_cache._logger, "exception") as mock_log,
    ):
        await sqlite_cache.save()
        mock_log.assert_called_once_with(
            "Error saving metadata to %s", sqlite_cache._db_path
        )


@pytest.mark.asyncio
async def test_clear_cache(sqlite_cache: AsyncSQLiteCache) -> None:
    """Test clearing the cache."""
    sqlite_cache._cache_data = {"recipe1": {"timestamp": "test"}}
    sqlite_cache._is_loaded = True

    await sqlite_cache.clear_cache()

    assert sqlite_cache._cache_data == {}


@pytest.mark.asyncio
async def test_get_item(sqlite_cache: AsyncSQLiteCache) -> None:
    """Test getting an item from the cache."""
    await sqlite_cache.load()
    item = await sqlite_cache.get_item("recipe1")
    assert item == {"timestamp": "test"}


@pytest.mark.asyncio
async def test_get_item_calls_load_if_not_loaded(
    sqlite_cache: AsyncSQLiteCache,
) -> None:
    """Test that get_item() triggers load() if the cache is not loaded."""
    sqlite_cache._is_loaded = False
    with patch.object(sqlite_cache, "load") as mock_load:
        await sqlite_cache.get_item("recipe1")
        mock_load.assert_called_once()


@pytest.mark.asyncio
async def test_get_item_returns_none_if_key_not_found(
    sqlite_cache: AsyncSQLiteCache,
) -> None:
    """Test that get_item() returns None if the key is not found."""
    sqlite_cache._is_loaded = True
    sqlite_cache._cache_data = {"recipe1": {"timestamp": "test"}}
    item = await sqlite_cache.get_item("non_existent_key")
    assert item is None


@pytest.mark.asyncio
async def test_set_item(sqlite_cache: AsyncSQLiteCache) -> None:
    """Test setting an item in the cache."""
    await sqlite_cache.load()
    await sqlite_cache.set_item("recipe1", {"timestamp": "test"})

    assert "recipe1" in sqlite_cache._cache_data
    assert sqlite_cache._cache_data["recipe1"] == {"timestamp": "test"}


@pytest.mark.asyncio
async def test_delete_item(sqlite_cache: AsyncSQLiteCache) -> None:
    """Test deleting an item from the cache."""
    await sqlite_cache.load()
    await sqlite_cache.set_item("recipe1", {"timestamp": "test"})
    assert "recipe1" in sqlite_cache._cache_data

    await sqlite_cache.delete_item("recipe1")
    assert "recipe1" not in sqlite_cache._cache_data


@pytest.mark.asyncio
async def test_delete_non_existent_key(sqlite_cache: AsyncSQLiteCache) -> None:
    """Test that delete_item() does not throw if the key does not exist."""
    sqlite_cache._is_loaded = True
    sqlite_cache._cache_data = {"recipe1": {"timestamp": "test"}}
    await sqlite_cache.delete_item("non_existent_key")  # Should not raise an error
    assert "recipe1" in sqlite_cache._cache_data


@pytest.mark.asyncio
async def test_open(sqlite_cache: AsyncSQLiteCache) -> None:
    """Test that `self._conn` exists after opening."""
    await sqlite_cache.open()
    assert hasattr(sqlite_cache, "_conn")


@pytest.mark.asyncio
async def test_close(sqlite_cache: AsyncSQLiteCache) -> None:
    """Test that `self._conn` does not exist after closing."""
    await sqlite_cache.open()
    await sqlite_cache.close()
    assert not hasattr(sqlite_cache, "_conn")
