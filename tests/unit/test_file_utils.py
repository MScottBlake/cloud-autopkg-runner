"""Tests for the file_utils module."""

import errno
import json
import logging
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

if sys.platform == "win32":  # xattr publishes no Windows build
    xattr = None
else:
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


@pytest.mark.skipif(
    sys.platform == "win32", reason="Windows has no extended attributes"
)
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

    # The names are spelled out rather than taken from file_utils, since the
    # point is that they match what URLDownloader.clear_vars() looks up.
    prefix = "user." if sys.platform.startswith("linux") else ""
    etag_attr = f"{prefix}com.github.autopkg.etag"
    last_modified_attr = f"{prefix}com.github.autopkg.last-modified"

    # getxattr() looks the name up in listxattr() before reading it.
    listed = xattr.listxattr(file_path)
    assert etag_attr in listed
    assert last_modified_attr in listed
    assert xattr.getxattr(file_path, etag_attr).decode() == '"3f8a9c1d"'
    assert (
        xattr.getxattr(file_path, last_modified_attr).decode()
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


def test_create_and_set_attrs_survives_unwritable_attrs(
    tmp_path: Path, mock_xattr: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    """A file system that rejects extended attributes must not fail the run."""
    file_path = tmp_path / "placeholder.dmg"
    mock_xattr.setxattr.side_effect = OSError(errno.ENOTSUP, "Operation not supported")

    with caplog.at_level(logging.WARNING):
        file_utils._create_and_set_attrs(
            file_path,
            {"file_path": str(file_path), "file_size": 1024, "etag": "test_etag"},
        )

    assert file_path.stat().st_size == 1024
    assert "Could not set extended attributes" in caplog.text


def test_create_and_set_attrs_without_xattr_support(tmp_path: Path) -> None:
    """Without extended attributes the placeholder is still created at size."""
    file_path = tmp_path / "placeholder.dmg"

    with patch("cloud_autopkg_runner.file_utils.xattr", new=None):
        file_utils._create_and_set_attrs(
            file_path,
            {"file_path": str(file_path), "file_size": 1024, "etag": "test_etag"},
        )

    assert file_path.stat().st_size == 1024


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
async def test_create_placeholder_files_survives_a_failure(
    tmp_path: Path, metadata_cache: MetadataCache, caplog: pytest.LogCaptureFixture
) -> None:
    """One unwritable placeholder must not cost the rest of the run."""
    settings = Settings()
    settings.cache_file = tmp_path / "metatadata_cache.json"
    settings.cache_file.write_text(json.dumps(metadata_cache))
    recipe_list = ["Recipe1", "Recipe2"]
    file_path1 = tmp_path / "path/to/file1.dmg"
    file_path2 = tmp_path / "path/to/file2.pkg"

    real_create = file_utils._create_and_set_attrs

    def fail_for_file1(file_path: Path, metadata: Any) -> None:
        """Fail the first placeholder the way a read-only volume would."""
        if file_path == file_path1:
            raise OSError(errno.EROFS, "Read-only file system")
        real_create(file_path, metadata)

    with (
        patch(
            "cloud_autopkg_runner.autopkg_prefs.AutoPkgPrefs._get_preference_file_contents",
            return_value={},
        ),
        patch(
            "cloud_autopkg_runner.recipe_finder.RecipeFinder.possible_file_names",
            return_value=recipe_list,
        ),
        patch(
            "cloud_autopkg_runner.file_utils._create_and_set_attrs",
            side_effect=fail_for_file1,
        ),
        caplog.at_level(logging.WARNING),
    ):
        await file_utils.create_placeholder_files(recipe_list)

    assert not file_path1.exists()
    assert file_path2.stat().st_size == 2048
    assert "Could not create placeholder" in caplog.text


@pytest.mark.asyncio
async def test_create_placeholder_files_reraises_unexpected_errors(
    tmp_path: Path, metadata_cache: MetadataCache
) -> None:
    """Only file system errors are absorbed; anything else still surfaces."""
    settings = Settings()
    settings.cache_file = tmp_path / "metatadata_cache.json"
    settings.cache_file.write_text(json.dumps(metadata_cache))
    recipe_list = ["Recipe1", "Recipe2"]

    with (
        patch(
            "cloud_autopkg_runner.autopkg_prefs.AutoPkgPrefs._get_preference_file_contents",
            return_value={},
        ),
        patch(
            "cloud_autopkg_runner.recipe_finder.RecipeFinder.possible_file_names",
            return_value=recipe_list,
        ),
        patch(
            "cloud_autopkg_runner.file_utils._create_and_set_attrs",
            side_effect=ValueError("boom"),
        ),
        pytest.raises(ValueError, match="boom"),
    ):
        await file_utils.create_placeholder_files(recipe_list)


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

    # Linux only accepts names in a known namespace, so an unprefixed name
    # would fail with EOPNOTSUPP rather than reporting the attribute as unset.
    attr = "non_existant_attr" if sys.platform == "darwin" else "user.non_existant_attr"

    result = await file_utils.get_file_metadata(file_path, attr)

    assert result is None


@pytest.mark.asyncio
async def test_get_file_metadata_without_xattr_support(tmp_path: Path) -> None:
    """Without extended attributes, metadata reads report the value as absent."""
    file_path = tmp_path / "test_file.txt"
    file_path.touch()

    with patch("cloud_autopkg_runner.file_utils.xattr", new=None):
        result = await file_utils.get_file_metadata(file_path, "test_attr")

    assert result is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("errno_to_simulate", "expect_warning"),
    [
        # An unset attribute is the ordinary case, and stays quiet.
        # ENOATTR on macOS, ENODATA on Linux; both mean "attribute not set"
        (file_utils._ENOATTR, False),
        (errno.ENODATA, False),
        # A read that fails is reported, but never raised at the caller
        (errno.ENOTSUP, True),
        (errno.EIO, True),
    ],
)
async def test_get_file_metadata_errno_behavior(
    tmp_path: Path,
    mock_xattr: MagicMock,
    caplog: pytest.LogCaptureFixture,
    errno_to_simulate: int,
    expect_warning: bool,
) -> None:
    """A metadata read never raises, whatever the file system reports.

    Losing the metadata costs a re-download on the next run. Failing the run
    over it would cost far more, so every errno reads as "no value", and only
    the unexpected ones are reported.
    """
    mock_file_path = tmp_path / "testfile.txt"
    mock_attr = file_utils.XATTR_ETAG

    # Set up the mock to raise the specified OSError
    mock_xattr.getxattr.side_effect = OSError(
        errno_to_simulate, f"Simulated error for errno {errno_to_simulate}"
    )

    with caplog.at_level(logging.WARNING):
        result = await file_utils.get_file_metadata(mock_file_path, mock_attr)

    assert result is None, (
        f"Expected None for errno {errno_to_simulate}, but got {result}"
    )
    warned = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert bool(warned) is expect_warning

    # Assert that xattr.getxattr was called as expected in all cases
    mock_xattr.getxattr.assert_called_once_with(mock_file_path, mock_attr)


@pytest.mark.asyncio
async def test_get_file_size(tmp_path: Path) -> None:
    """Test getting file size."""
    file_path = tmp_path / "test_file.txt"
    file_path.write_bytes(b"test_content")

    result = await file_utils.get_file_size(file_path)

    assert result == len(b"test_content")
