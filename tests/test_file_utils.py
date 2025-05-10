"""Tests for the file_utils module."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from cloud_autopkg_runner import (
    Settings,
    file_utils,
)
from cloud_autopkg_runner.metadata_cache import MetadataCache


@pytest.fixture
def mock_xattr() -> Any:
    """Fixture to mock the xattr module.

    Yields:
        Any: The mock xattr module.
    """
    with patch("cloud_autopkg_runner.file_utils.xattr") as mock:
        yield mock


@pytest.fixture
def metadata_cache(tmp_path: Path) -> MetadataCache:
    """Fixture for a sample metadata cache.

    Returns:
        MetadataCache: A sample metadata cache.
    """
    return {
        "Recipe1": {
            "timestamp": "foo",
            "metadata": [
                {
                    "file_path": f"{tmp_path}/path/to/file1.dmg",
                    "file_size": 1024,
                    "etag": "test_etag",
                    "last_modified": "test_last_modified",
                }
            ],
        },
        "Recipe2": {
            "timestamp": "foo",
            "metadata": [
                {
                    "file_path": f"{tmp_path}/path/to/file2.pkg",
                    "file_size": 2048,
                    "etag": "another_etag",
                    "last_modified": "another_last_modified",
                }
            ],
        },
    }


@pytest.mark.asyncio
async def test_create_dummy_files(
    tmp_path: Path, metadata_cache: MetadataCache
) -> None:
    """Test creating dummy files based on metadata."""
    settings = Settings()
    settings.cache_file = tmp_path / "metatadata_cache.json"
    settings.cache_file.write_text(json.dumps(metadata_cache))
    recipe_list = ["Recipe1", "Recipe2"]
    file_path1 = tmp_path / "path/to/file1.dmg"
    file_path2 = tmp_path / "path/to/file2.pkg"

    # Patch list_possible_file_names to return the recipes in metadata_cache
    with (
        patch(
            "cloud_autopkg_runner.recipe_finder.RecipeFinder.possible_file_names",
            return_value=recipe_list,
        ),
    ):
        await file_utils.create_dummy_files(recipe_list)

    assert file_path1.exists()
    assert file_path1.stat().st_size == 1024
    assert file_path2.exists()
    assert file_path2.stat().st_size == 2048


@pytest.mark.asyncio
async def test_create_dummy_files_skips_existing(
    tmp_path: Path, metadata_cache: MetadataCache
) -> None:
    """Test skipping creation of existing dummy files."""
    settings = Settings()
    settings.cache_file = tmp_path / "metatadata_cache.json"
    settings.cache_file.write_text(json.dumps(metadata_cache))
    recipe_list = ["Recipe1"]
    file_path = tmp_path / "path/to/file1.dmg"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.touch()

    # Patch list_possible_file_names to return the recipes in metadata_cache
    with patch(
        "cloud_autopkg_runner.recipe_finder.RecipeFinder.possible_file_names",
        return_value=recipe_list,
    ):
        await file_utils.create_dummy_files(recipe_list)

    assert file_path.exists()
    assert file_path.stat().st_size == 0  # Size remains 0 as it was skipped


@pytest.mark.asyncio
async def test_get_file_metadata(tmp_path: Path, mock_xattr: Any) -> None:
    """Test getting file metadata."""
    file_path = tmp_path / "test_file.txt"
    file_path.touch()
    mock_xattr.getxattr.return_value = b"test_value"

    result = await file_utils.get_file_metadata(file_path, "test_attr")

    mock_xattr.getxattr.assert_called_with(file_path, "test_attr")
    assert result == "test_value"


@pytest.mark.asyncio
async def test_get_file_size(tmp_path: Path) -> None:
    """Test getting file size."""
    file_path = tmp_path / "test_file.txt"
    file_path.write_bytes(b"test_content")

    result = await file_utils.get_file_size(file_path)

    assert result == len(b"test_content")
