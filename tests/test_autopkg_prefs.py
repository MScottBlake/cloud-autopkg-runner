import plistlib
from pathlib import Path
from typing import Any

import pytest

from cloud_autopkg_runner.autopkg_prefs import AutoPkgPrefs
from cloud_autopkg_runner.exceptions import (
    InvalidPlistContents,
    PreferenceFileNotFoundError,
    PreferenceKeyNotFoundError,
)


def create_dummy_plist(content: dict[str, Any], path: Path) -> None:
    """Creates a dummy plist file for testing."""
    if path.exists():
        path.unlink()
    path.write_bytes(plistlib.dumps(content))


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

    assert prefs.cache_dir == cache_dir
    assert prefs.recipe_override_dirs == [Path(path) for path in override_dirs]
    assert prefs.recipe_search_dirs == [Path(path) for path in override_dirs]
    assert prefs.recipe_repo_dir == Path(str(tmp_path))
    assert prefs.munki_repo == munki_repo


def test_autopkgprefs_init_with_nonexistent_plist(tmp_path: Path) -> None:
    """Test initializing AutoPkgPrefs with a non-existent plist file."""
    prefs_file = tmp_path / "nonexistent.plist"
    if prefs_file.exists():
        prefs_file.unlink()

    with pytest.raises(PreferenceFileNotFoundError):
        AutoPkgPrefs(prefs_file)


def test_autopkgprefs_init_with_invalid_plist(tmp_path: Path) -> None:
    """Test initializing AutoPkgPrefs with an invalid plist file."""
    plist_path = tmp_path / "invalid.plist"
    plist_path.write_text("invalid file")

    with pytest.raises(InvalidPlistContents):
        AutoPkgPrefs(plist_path)


def test_autopkgprefs_known_key_properties(tmp_path: Path) -> None:
    """Test accessing a known preference using property access."""
    cache_dir = str(tmp_path / "cache")
    override_dirs = [str(tmp_path / "overrides")]
    plist_content = {
        "CACHE_DIR": cache_dir,
        "RECIPE_OVERRIDE_DIRS": override_dirs,
    }
    plist_path = tmp_path / "test.plist"
    create_dummy_plist(plist_content, plist_path)

    prefs = AutoPkgPrefs(plist_path)

    assert prefs.cache_dir == Path(cache_dir)
    assert prefs.recipe_override_dirs == [Path(path) for path in override_dirs]


def test_autopkgprefs_get_known_key(tmp_path: Path) -> None:
    """Test getting a known preference using get()."""
    cache_dir = tmp_path / "cache"
    plist_content = {"CACHE_DIR": str(cache_dir)}
    plist_path = tmp_path / "test.plist"
    create_dummy_plist(plist_content, plist_path)

    prefs = AutoPkgPrefs(plist_path)

    assert prefs.get("CACHE_DIR") == cache_dir
    assert prefs.get("CACHE_DIR", "default_value") == cache_dir


def test_autopkgprefs_get_nonexistent_key(tmp_path: Path) -> None:
    """Test getting a nonexistent preference using get()."""
    plist_path = tmp_path / "test.plist"
    create_dummy_plist({}, plist_path)

    prefs = AutoPkgPrefs(plist_path)

    assert prefs.get("NonExistentKey") is None
    assert prefs.get("NonExistentKey", "default_value") == "default_value"


def test_autopkgprefs_getattr_known_key(tmp_path: Path) -> None:
    """Test accessing a known preference using getattr()."""
    cache_dir = tmp_path / "cache"
    plist_content = {"CACHE_DIR": str(cache_dir)}
    plist_path = tmp_path / "test.plist"
    create_dummy_plist(plist_content, plist_path)

    prefs = AutoPkgPrefs(plist_path)

    assert prefs.cache_dir == cache_dir


def test_autopkgprefs_getattr_nonexistent_key(tmp_path: Path) -> None:
    """Test accessing a nonexistent preference using getattr()."""
    plist_path = tmp_path / "test.plist"
    create_dummy_plist({}, plist_path)

    prefs = AutoPkgPrefs(plist_path)

    with pytest.raises(PreferenceKeyNotFoundError):
        _ = prefs.NonExistentKey
