import plistlib
from pathlib import Path
from typing import Any

import pytest

from cloud_autopkg_runner.autopkg_prefs import AutoPkgPrefs
from cloud_autopkg_runner.exceptions import (
    AutoPkgRunnerException,
    InvalidPlistContents,
)


def create_dummy_plist(content: dict[str, Any], path: Path) -> None:
    """Creates a dummy plist file for testing."""
    with path.open("wb") as fp:
        plistlib.dump(content, fp)


def test_init_with_existing_plist(tmp_path: Path) -> None:
    """Test initializing AutoPkgPrefs with an existing plist file."""
    cache_dir = tmp_path / "cache"
    override_dirs = [str(tmp_path / "overrides")]
    munki_repo = tmp_path / "munki"

    plist_content = {
        "CACHE_DIR": str(cache_dir),
        "RECIPE_OVERRIDE_DIRS": override_dirs,
        "RECIPE_SEARCH_DIRS": override_dirs,
        "RECIPE_REPO_DIR": str(tmp_path),
        "MUNKI_REPO": str(munki_repo),
    }

    plist_path = tmp_path / "test.plist"
    create_dummy_plist(plist_content, plist_path)

    prefs = AutoPkgPrefs(plist_path)

    assert prefs["CACHE_DIR"] == cache_dir
    assert prefs["RECIPE_OVERRIDE_DIRS"] == [Path(path) for path in override_dirs]
    assert prefs["RECIPE_SEARCH_DIRS"] == [Path(path) for path in override_dirs]
    assert prefs["RECIPE_REPO_DIR"] == Path(str(tmp_path))
    assert prefs["MUNKI_REPO"] == munki_repo


def test_autopkgprefs_init_with_nonexistent_plist(tmp_path: Path) -> None:
    """Test initializing AutoPkgPrefs with a non-existent plist file."""
    prefs_file = tmp_path / "nonexistent.plist"
    if prefs_file.exists():
        prefs_file.unlink()

    with pytest.raises(AutoPkgRunnerException):
        AutoPkgPrefs(prefs_file)


@pytest.mark.asyncio
async def test_autopkgprefs_init_with_invalid_plist(tmp_path: Path) -> None:
    """Test initializing AutoPkgPrefs with an invalid plist file."""
    plist_path = tmp_path / "invalid.plist"
    plist_path.write_text("invalid file")

    with pytest.raises(InvalidPlistContents):
        AutoPkgPrefs(plist_path)


def test_autopkgprefs_getitem_known_key(tmp_path: Path) -> None:
    """Test accessing a known preference using __getitem__."""
    cache_dir = str(tmp_path / "cache")
    plist_content = {"CACHE_DIR": cache_dir}
    plist_path = tmp_path / "test.plist"
    create_dummy_plist(plist_content, plist_path)

    prefs = AutoPkgPrefs(plist_path)

    assert prefs["CACHE_DIR"] == Path(cache_dir)


def test_autopkgprefs_getitem_recipedirs_string(tmp_path: Path) -> None:
    """Test accessing a known preference that has a string as the type.

    There is an issue where .plist will be interpreted as a list even when it's not.
    """
    cache_dir = str(tmp_path / "cache")
    plist_content = {"RECIPE_OVERRIDE_DIRS": cache_dir}
    plist_path = tmp_path / "test.plist"
    create_dummy_plist(plist_content, plist_path)

    prefs = AutoPkgPrefs(plist_path)
    assert prefs["RECIPE_OVERRIDE_DIRS"] == [Path(cache_dir)]


def test_autopkgprefs_setitem(tmp_path: Path) -> None:
    """Test setting preferences using __setitem__."""
    plist_content = {"CACHE_DIR": str(tmp_path / "cache")}
    plist_path = tmp_path / "test.plist"
    create_dummy_plist(plist_content, plist_path)

    prefs = AutoPkgPrefs(plist_path)

    prefs["NewKey"] = "NewValue"
    assert prefs["NewKey"] == "NewValue"

    prefs["CACHE_DIR"] = Path("/new/cache/dir")
    assert prefs["CACHE_DIR"] == Path("/new/cache/dir")


def test_autopkgprefs_get_known_key(tmp_path: Path) -> None:
    """Test getting a known preference using get()."""
    cache_dir = str(tmp_path / "cache")
    plist_content = {"CACHE_DIR": cache_dir}
    plist_path = tmp_path / "test.plist"
    create_dummy_plist(plist_content, plist_path)

    prefs = AutoPkgPrefs(plist_path)

    assert prefs.get("CACHE_DIR") == Path(cache_dir)
    assert prefs.get("CACHE_DIR", "default_value") == Path(cache_dir)


def test_autopkgprefs_get_nonexistent_key(tmp_path: Path) -> None:
    """Test getting a nonexistent preference using get()."""
    plist_path = tmp_path / "test.plist"
    create_dummy_plist({}, plist_path)

    prefs = AutoPkgPrefs(plist_path)

    assert prefs.get("NonExistentKey") is None
    assert prefs.get("NonExistentKey", "default_value") == "default_value"
