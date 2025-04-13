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


def test_autopkgprefs_init_default_plist(tmp_path: Path) -> None:
    """Test initializing AutoPkgPrefs with no plist file parameter."""
    prefs_file = Path("~/Library/Preferences/com.github.autopkg.plist").expanduser()
    if not prefs_file.exists():
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
        create_dummy_plist(plist_content, prefs_file)

    AutoPkgPrefs()
    assert AutoPkgPrefs().recipe_override_dirs != []
    assert AutoPkgPrefs().recipe_search_dirs != []


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
    override_dir = str(tmp_path / "overrides")
    override_dirs = [str(tmp_path / "overrides")]
    plist_content = {
        "CACHE_DIR": cache_dir,
        "RECIPE_OVERRIDE_DIRS": override_dirs,
        "RECIPE_SEARCH_DIRS": override_dir,
    }
    plist_path = tmp_path / "test.plist"
    create_dummy_plist(plist_content, plist_path)

    prefs = AutoPkgPrefs(plist_path)

    assert prefs.cache_dir == Path(cache_dir)
    assert prefs.recipe_override_dirs == [Path(path) for path in override_dirs]
    assert prefs.recipe_search_dirs == [Path(path) for path in override_dirs]


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
    mock_api_key = "FakeApiKey"
    mock_username = "FakeUsername"
    mock_password = "FakePassword"  # noqa: S105
    mock_token = "FakeToken"  # noqa: S105
    plist_content = {
        "BES_PASSWORD": mock_password,
        "BES_USERNAME": mock_username,
        "CACHE_DIR": str(cache_dir),
        "CLOUD_DP": False,
        "FAIL_RECIPES_WITHOUT_TRUST_INFO": True,
        "FW_ADMIN_PASSWORD": mock_password,
        "FW_ADMIN_USER": mock_username,
        "GITHUB_TOKEN": mock_token,
        "JC_API": mock_api_key,
        "JC_ORG": "FakeOrgId",
        "PATCH_TOKEN": mock_token,
        "SMB_PASSWORD": mock_password,
        "SMB_URL": "smb://fake.url",
        "SMB_USERNAME": mock_username,
        "VIRUSTOTAL_API_KEY": mock_api_key,
    }
    plist_path = tmp_path / "test.plist"
    create_dummy_plist(plist_content, plist_path)

    prefs = AutoPkgPrefs(plist_path)

    assert prefs.cache_dir == cache_dir
    assert prefs.github_token == mock_token
    assert prefs.smb_url == "smb://fake.url"
    assert prefs.smb_username == mock_username
    assert prefs.smb_password == mock_password
    assert prefs.patch_url is None
    assert prefs.patch_token == mock_token
    assert prefs.title_url is None
    assert prefs.title_user is None
    assert prefs.title_pass is None
    assert prefs.jc_api == mock_api_key
    assert prefs.jc_org == "FakeOrgId"
    assert prefs.fw_server_host is None
    assert prefs.fw_server_port is None
    assert prefs.fw_admin_user == mock_username
    assert prefs.fw_admin_password == mock_password
    assert prefs.bes_root_server is None
    assert prefs.bes_username == mock_username
    assert prefs.bes_password == mock_password
    assert prefs.client_id is None
    assert prefs.client_secret is None
    assert prefs.tenant_id is None
    assert prefs.virustotal_api_key == mock_api_key
    assert prefs.fail_recipes_without_trust_info is True
    assert prefs.stop_if_no_jss_upload is None
    assert prefs.cloud_dp is False
    assert prefs.smb_shares is None


def test_autopkgprefs_getattr_nonexistent_key(tmp_path: Path) -> None:
    """Test accessing a nonexistent preference using getattr()."""
    plist_path = tmp_path / "test.plist"
    create_dummy_plist({}, plist_path)

    prefs = AutoPkgPrefs(plist_path)

    with pytest.raises(PreferenceKeyNotFoundError):
        _ = prefs.NonExistentKey
