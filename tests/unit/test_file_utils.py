"""Tests for the file_utils module."""

import errno
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import xattr

from cloud_autopkg_runner import Settings, file_utils
from cloud_autopkg_runner.exceptions import InvalidFileSizeError
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


@pytest.mark.parametrize("size", [0, 1, 1024])
def test_set_file_size(tmp_path: Path, size: int) -> None:
    """A file is reported at the requested size, including zero."""
    file_path = tmp_path / "placeholder.dmg"

    file_utils._set_file_size(file_path, size)

    assert file_path.stat().st_size == size


def test_set_file_size_rejects_negative(tmp_path: Path) -> None:
    """A negative size is rejected rather than raising a bare OSError."""
    file_path = tmp_path / "placeholder.dmg"

    with pytest.raises(InvalidFileSizeError):
        file_utils._set_file_size(file_path, -1)


def test_placeholder_satisfies_urldownloader(tmp_path: Path) -> None:
    """A placeholder must survive the checks AutoPkg's URLDownloader makes.

    URLDownloader deletes any empty file before reading its xattrs
    (clear_zero_file), then reads the size and the etag/last-modified xattrs
    to build its conditional request (produce_etag_headers). It never reads
    the file's contents.
    """
    file_path = tmp_path / "GoogleChrome" / "googlechrome.dmg"
    file_utils._create_and_set_attrs(
        file_path,
        {
            "file_path": str(file_path),
            "file_size": 219045888,
            "etag": '"3f8a9c1d"',
            "last_modified": "Wed, 21 Oct 2025 07:28:00 GMT",
        },
    )

    # clear_zero_file() would delete anything empty.
    assert file_path.stat().st_size != 0

    # produce_etag_headers() reports this as existing_file_size.
    assert file_path.stat().st_size == 219045888

    # getxattr() looks the name up in listxattr() before reading it.
    listed = xattr.listxattr(file_path)
    assert "com.github.autopkg.etag" in listed
    assert "com.github.autopkg.last-modified" in listed
    assert xattr.getxattr(file_path, "com.github.autopkg.etag").decode() == '"3f8a9c1d"'
    assert (
        xattr.getxattr(file_path, "com.github.autopkg.last-modified").decode()
        == "Wed, 21 Oct 2025 07:28:00 GMT"
    )


def test_create_and_set_attrs_with_absent_file_size(
    tmp_path: Path, mock_xattr: Any
) -> None:
    """Metadata with no file_size falls back to 0 without raising."""
    file_path = tmp_path / "nested" / "placeholder.dmg"

    file_utils._create_and_set_attrs(file_path, {"file_path": str(file_path)})

    assert file_path.stat().st_size == 0
    mock_xattr.setxattr.assert_not_called()


@pytest.mark.asyncio
async def test_create_placeholder_files_skips_zero_size(tmp_path: Path) -> None:
    """A cached size of zero is skipped, since AutoPkg discards empty files."""
    settings = Settings()
    settings.cache_file = tmp_path / "metadata_cache.json"
    file_path = tmp_path / "path/to/empty.dmg"
    settings.cache_file.write_text(
        json.dumps(
            {
                "Recipe1": {
                    "timestamp": "foo",
                    "metadata": [{"file_path": str(file_path), "file_size": 0}],
                }
            }
        )
    )

    with (
        patch(
            "cloud_autopkg_runner.autopkg_prefs.AutoPkgPrefs._get_preference_file_contents",
            return_value={},
        ),
        patch(
            "cloud_autopkg_runner.recipe_finder.RecipeFinder.possible_file_names",
            return_value=["Recipe1"],
        ),
    ):
        await file_utils.create_placeholder_files(["Recipe1"])

    assert not file_path.exists()


@pytest.mark.asyncio
async def test_create_placeholder_files_skips_negative_size(tmp_path: Path) -> None:
    """A corrupt negative size is skipped without failing the whole run."""
    settings = Settings()
    settings.cache_file = tmp_path / "metadata_cache.json"
    bad_path = tmp_path / "path/to/bad.dmg"
    good_path = tmp_path / "path/to/good.dmg"
    settings.cache_file.write_text(
        json.dumps(
            {
                "Recipe1": {
                    "timestamp": "foo",
                    "metadata": [
                        {"file_path": str(bad_path), "file_size": -1},
                        {"file_path": str(good_path), "file_size": 512},
                    ],
                }
            }
        )
    )

    with (
        patch(
            "cloud_autopkg_runner.autopkg_prefs.AutoPkgPrefs._get_preference_file_contents",
            return_value={},
        ),
        patch(
            "cloud_autopkg_runner.recipe_finder.RecipeFinder.possible_file_names",
            return_value=["Recipe1"],
        ),
    ):
        await file_utils.create_placeholder_files(["Recipe1"])

    assert not bad_path.exists()
    assert good_path.stat().st_size == 512


@pytest.mark.asyncio
async def test_create_placeholder_files(
    tmp_path: Path, metadata_cache: MetadataCache
) -> None:
    """Test creating placeholder files based on metadata."""
    settings = Settings()
    settings.cache_file = tmp_path / "metatadata_cache.json"
    settings.cache_file.write_text(json.dumps(metadata_cache))
    recipe_list = ["Recipe1", "Recipe2"]
    file_path1 = tmp_path / "path/to/file1.dmg"
    file_path2 = tmp_path / "path/to/file2.pkg"

    # Patch list_possible_file_names to return the recipes in metadata_cache
    with (
        patch(
            "cloud_autopkg_runner.autopkg_prefs.AutoPkgPrefs._get_preference_file_contents",
            return_value={},
        ),
        patch(
            "cloud_autopkg_runner.recipe_finder.RecipeFinder.possible_file_names",
            return_value=recipe_list,
        ),
    ):
        await file_utils.create_placeholder_files(recipe_list)

    assert file_path1.exists()
    assert file_path1.stat().st_size == 1024
    assert file_path2.exists()
    assert file_path2.stat().st_size == 2048


@pytest.mark.asyncio
async def test_create_placeholder_files_skips_existing(
    tmp_path: Path, metadata_cache: MetadataCache
) -> None:
    """Test skipping creation of existing placeholder files."""
    settings = Settings()
    settings.cache_file = tmp_path / "metatadata_cache.json"
    settings.cache_file.write_text(json.dumps(metadata_cache))
    recipe_list = ["Recipe1"]
    file_path = tmp_path / "path/to/file1.dmg"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.touch()

    # Patch list_possible_file_names to return the recipes in metadata_cache
    with (
        patch(
            "cloud_autopkg_runner.autopkg_prefs.AutoPkgPrefs._get_preference_file_contents",
            return_value={},
        ),
        patch(
            "cloud_autopkg_runner.recipe_finder.RecipeFinder.possible_file_names",
            return_value=recipe_list,
        ),
    ):
        await file_utils.create_placeholder_files(recipe_list)

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
async def test_get_file_metadata_invalid_attr(tmp_path: Path) -> None:
    """Test getting file metadata."""
    file_path = tmp_path / "test_file.txt"
    file_path.touch()

    result = await file_utils.get_file_metadata(file_path, "non_existant_attr")

    assert result is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("platform", "errno_to_simulate", "expected_result_is_none"),
    [
        # --- Cases where None should be returned ---
        ("darwin", errno.ENOATTR, True),
        ("linux", errno.ENODATA, True),
        ("win32", errno.ENODATA, True),
        ("darwin", errno.ENODATA, True),
        # --- Cases where OSError should be re-raised ---
        ("linux", errno.ENOATTR, False),
        ("win32", errno.ENOATTR, False),
        ("darwin", errno.EIO, False),
        ("linux", errno.EIO, False),
    ],
)
async def test_get_file_metadata_errno_behavior(
    tmp_path: Path,
    mock_xattr: MagicMock,
    platform: str,
    errno_to_simulate: int,
    expected_result_is_none: bool,
) -> None:
    """Test get_file_metadata's platform-specific errno handling.

    This test uses parametrization to cover:
    - Returning None for specific 'attribute not found' errors.
    - Re-raising OSErrors for other errno codes.
    - Simulating different platforms using `sys.platform`.
    """
    mock_file_path = tmp_path / "testfile.txt"
    mock_attr = "com.github.autopkg.etag"

    # Set up the mock to raise the specified OSError
    mock_xattr.getxattr.side_effect = OSError(
        errno_to_simulate, f"Simulated error for errno {errno_to_simulate}"
    )

    with patch.object(sys, "platform", new=platform):
        if expected_result_is_none:
            result = await file_utils.get_file_metadata(mock_file_path, mock_attr)
            assert result is None, (
                f"Expected None for errno {errno_to_simulate} on {platform}, "
                f"but got {result}"
            )
        else:
            with pytest.raises(OSError) as exc_info:  # noqa: PT011
                await file_utils.get_file_metadata(mock_file_path, mock_attr)
            assert exc_info.type is OSError
            assert exc_info.value.errno == errno_to_simulate, (
                f"Expected OSError with errno {errno_to_simulate} on {platform}, "
                f"but got {exc_info.value.errno}"
            )

        # Assert that xattr.getxattr was called as expected in all cases
        mock_xattr.getxattr.assert_called_once_with(mock_file_path, mock_attr)
        mock_xattr.getxattr.reset_mock()  # Reset for the next parameter iteration


@pytest.mark.asyncio
async def test_get_file_size(tmp_path: Path) -> None:
    """Test getting file size."""
    file_path = tmp_path / "test_file.txt"
    file_path.write_bytes(b"test_content")

    result = await file_utils.get_file_size(file_path)

    assert result == len(b"test_content")
