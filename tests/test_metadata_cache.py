import asyncio
import json
from pathlib import Path

import pytest

from cloud_autopkg_runner.exceptions import InvalidJsonContents
from cloud_autopkg_runner.metadata_cache import (
    MetadataCache,
    MetadataCacheManager,
    RecipeCache,
)


@pytest.fixture
def empty_metadata_cache(tmp_path: Path) -> Path:
    """Fixture that creates a temporary empty metadata cache file."""
    cache_file = tmp_path / "cache.json"
    cache_file.write_text("{}")
    return cache_file


@pytest.mark.asyncio
async def test_load_metadata_cache_from_disk(empty_metadata_cache: Path) -> None:
    """Test loading the metadata cache from disk."""
    await MetadataCacheManager.clear_cache()
    cache_file = empty_metadata_cache
    cache_data: MetadataCache = {"Recipe1": {"timestamp": "123", "metadata": []}}
    cache_file.write_text(json.dumps(cache_data))  # Overwrite with test data

    loaded_cache = await MetadataCacheManager.load(cache_file)
    assert loaded_cache == cache_data


@pytest.mark.asyncio
async def test_load_metadata_cache_nonexistent_file(tmp_path: Path) -> None:
    """Test loading metadata cache from a non-existent JSON file."""
    await MetadataCacheManager.clear_cache()
    cache_file = tmp_path / "cache.json"

    # Ensure the file doesn't exist
    if cache_file.exists():
        cache_file.unlink()

    loaded_cache = await MetadataCacheManager.load(cache_file)
    assert loaded_cache == {}
    assert cache_file.exists()


@pytest.mark.asyncio
async def test_load_metadata_cache_invalid_json(empty_metadata_cache: Path) -> None:
    """Test loading metadata cache with invalid JSON content."""
    await MetadataCacheManager.clear_cache()
    cache_file = empty_metadata_cache
    cache_file.write_text("invalid json")

    with pytest.raises(InvalidJsonContents):
        await MetadataCacheManager.load(cache_file)


@pytest.mark.asyncio
async def test_save_metadata_cache(empty_metadata_cache: Path) -> None:
    """Test saving metadata cache to a JSON file."""
    await MetadataCacheManager.clear_cache()
    cache_file = empty_metadata_cache
    recipe_name = "Recipe1"
    metadata: RecipeCache = {
        "timestamp": "456",
        "metadata": [{"file_path": "path/to/file", "file_size": 4096}],
    }

    await MetadataCacheManager.save(cache_file, recipe_name, metadata)

    loaded_cache = await MetadataCacheManager.load(cache_file)
    assert recipe_name in loaded_cache
    assert loaded_cache[recipe_name] == metadata


@pytest.mark.asyncio
async def test_save_metadata_cache_multiple_recipes(empty_metadata_cache: Path) -> None:
    """Test saving metadata cache with multiple recipes."""
    await MetadataCacheManager.clear_cache()
    cache_file = empty_metadata_cache
    recipe_name1 = "Recipe1"
    recipe_name2 = "Recipe2"
    metadata1: RecipeCache = {"timestamp": "456", "metadata": []}
    metadata2: RecipeCache = {"timestamp": "789", "metadata": []}

    await MetadataCacheManager.save(cache_file, recipe_name1, metadata1)
    await MetadataCacheManager.save(cache_file, recipe_name2, metadata2)

    # Load the cache and check if both recipes are present with correct data
    loaded_cache = await MetadataCacheManager.load(cache_file)
    assert recipe_name1 in loaded_cache
    assert recipe_name2 in loaded_cache
    assert loaded_cache[recipe_name1] == metadata1
    assert loaded_cache[recipe_name2] == metadata2


@pytest.mark.asyncio
async def test_consecutive_saves(empty_metadata_cache: Path) -> None:
    """Testing that back to back saving the file does not overwrite the other value."""
    await MetadataCacheManager.clear_cache()
    cache_file = empty_metadata_cache
    recipe_name1 = "Recipe1"
    recipe_name2 = "Recipe2"
    metadata1: RecipeCache = {"timestamp": "456", "metadata": []}
    metadata2: RecipeCache = {"timestamp": "789", "metadata": []}

    # Testing that saves and writes works fine if save happens concurrently
    await asyncio.gather(
        MetadataCacheManager.save(cache_file, recipe_name1, metadata1),
        MetadataCacheManager.save(cache_file, recipe_name2, metadata2),
    )

    loaded_cache = await MetadataCacheManager.load(cache_file)
    assert recipe_name1 in loaded_cache
    assert recipe_name2 in loaded_cache
    assert loaded_cache[recipe_name1] == metadata1
    assert loaded_cache[recipe_name2] == metadata2
