"""Module for managing AutoPkg preferences in cloud-autopkg-runner.

This module provides the `AutoPkgPrefs` class, which encapsulates
the logic for loading, accessing, and managing AutoPkg preferences
from a plist file (typically `~/Library/Preferences/com.github.autopkg.plist`).

The `AutoPkgPrefs` class supports type-safe access to well-known AutoPkg
preference keys, while also allowing access to arbitrary preferences
defined in the plist file. It handles the conversion of preference
values to the appropriate Python types (e.g., strings to Paths).

Key preferences managed include:
- Cache directory (`CACHE_DIR`)
- Recipe repository directory (`RECIPE_REPO_DIR`)
- Munki repository directory (`MUNKI_REPO`)
- Recipe search directories (`RECIPE_SEARCH_DIRS`)
- Recipe override directories (`RECIPE_OVERRIDE_DIRS`)
"""

import plistlib
from pathlib import Path
from typing import Any

from cloud_autopkg_runner.exceptions import (
    InvalidPlistContents,
    PreferenceFileNotFoundError,
    PreferenceKeyNotFoundError,
)

# Known Preference sources:
# - https://github.com/autopkg/autopkg/wiki/Preferences
# - https://github.com/grahampugh/jamf-upload/wiki/JamfUploader-AutoPkg-Processors
# - https://github.com/autopkg/lrz-recipes/blob/main/README.md
# - https://github.com/lazymacadmin/UpdateTitleEditor
# - https://github.com/TheJumpCloud/JC-AutoPkg-Importer/wiki/Arguments
# - https://github.com/autopkg/filewave/blob/master/README.md
# - https://github.com/CLCMacTeam/AutoPkgBESEngine/blob/master/README.md
# - https://github.com/almenscorner/intune-uploader/wiki/IntuneAppUploader
# - https://github.com/hjuutilainen/autopkg-virustotalanalyzer/blob/master/README.md


class AutoPkgPrefs:
    """Manages AutoPkg preferences loaded from a plist file.

    Provides methods for accessing known AutoPkg preferences and arbitrary
    preferences defined in the plist file. Handles type conversions
    for known preference keys.
    """

    def __init__(self, plist_path: Path | None = None) -> None:
        """Creates an AutoPkgPrefs object from a plist file.

        Loads the contents of the plist file, separates the known preferences
        from the extra preferences, and creates a new
        AutoPkgPrefs object.

        Args:
            plist_path: The path to the plist file. If None, defaults to
                `~/Library/Preferences/com.github.autopkg.plist`.

        Raises:
            AutoPkgRunnerException: If the specified plist file does not exist.
            InvalidPlistContents: If the specified plist file is invalid.
        """
        if not plist_path:
            plist_path = Path(
                "~/Library/Preferences/com.github.autopkg.plist"
            ).expanduser()

        # Set defaults
        self._prefs: dict[str, Any] = {
            "CACHE_DIR": Path("~/Library/AutoPkg/Cache").expanduser(),
            "RECIPE_SEARCH_DIRS": [
                Path(),
                Path("~/Library/AutoPkg/Recipes").expanduser(),
                Path("/Library/AutoPkg/Recipes"),
            ],
            "RECIPE_OVERRIDE_DIRS": [
                Path("~/Library/AutoPkg/RecipeOverrides").expanduser()
            ],
            "RECIPE_REPO_DIR": Path("~/Library/AutoPkg/RecipeRepos").expanduser(),
        }

        try:
            prefs: dict[str, Any] = plistlib.loads(plist_path.read_bytes())
        except FileNotFoundError as exc:
            raise PreferenceFileNotFoundError(plist_path) from exc
        except plistlib.InvalidFileException as exc:
            raise InvalidPlistContents(plist_path) from exc

        # Convert `str` to `Path`
        if "CACHE_DIR" in prefs:
            prefs["CACHE_DIR"] = Path(prefs["CACHE_DIR"]).expanduser()
        if "RECIPE_REPO_DIR" in prefs:
            prefs["RECIPE_REPO_DIR"] = Path(prefs["RECIPE_REPO_DIR"]).expanduser()
        if "MUNKI_REPO" in prefs:
            prefs["MUNKI_REPO"] = Path(prefs["MUNKI_REPO"]).expanduser()

        if "RECIPE_SEARCH_DIRS" in prefs:
            prefs["RECIPE_SEARCH_DIRS"] = self._convert_to_list_of_paths(
                prefs["RECIPE_SEARCH_DIRS"]
            )
        if "RECIPE_OVERRIDE_DIRS" in prefs:
            prefs["RECIPE_OVERRIDE_DIRS"] = self._convert_to_list_of_paths(
                prefs["RECIPE_OVERRIDE_DIRS"]
            )

        self._prefs.update(prefs)

    def _convert_to_list_of_paths(self, value: str | list[str]) -> list[Path]:
        """Converts a string or a list of strings to a list of Path objects.

        If the input is a string, it is treated as a single path and converted
        into a list containing that path. If the input is already a list of
        strings, each string is converted into a Path object. All paths are
        expanded to include the user's home directory.

        Args:
            value: A string representing a single path or a list of strings
                representing multiple paths.

        Returns:
            A list of Path objects, where each Path object represents a path
            from the input.
        """
        if isinstance(value, str):
            value = [value]
        return [Path(x).expanduser() for x in value]

    def __getattr__(self, name: str) -> object:
        """Retrieves a preference value by attribute name.

        This method allows accessing preferences as attributes of the
        AutoPkgPrefs object.

        Args:
            name: The name of the attribute to retrieve.

        Returns:
            The value of the preference, if found.

        Raises:
            PreferenceKeyNotFoundError: If the attribute name does not
                correspond to a preference.
        """
        try:
            return self._prefs[name]
        except KeyError as exc:
            raise PreferenceKeyNotFoundError(name) from exc

    def get(self, key: str, default: object = None) -> object:
        """Return the preference value for `key`, or `default` if not set.

        Args:
            key: The name of the preference to retrieve.
            default: The value to return if the key is not found.

        Returns:
            The value of the preference, or the default value if the key is not found.
        """
        return self._prefs.get(key, default)

    @property
    def cache_dir(self) -> Path:
        """Gets the cache directory path."""
        return self._prefs["CACHE_DIR"]

    @property
    def recipe_repo_dir(self) -> Path:
        """Gets the recipe repository directory path."""
        return self._prefs["RECIPE_REPO_DIR"]

    @property
    def munki_repo(self) -> Path | None:
        """Gets the Munki repository path, if set."""
        return self._prefs.get("MUNKI_REPO")

    @property
    def recipe_search_dirs(self) -> list[Path]:
        """Gets the list of recipe search directories."""
        return self._prefs["RECIPE_SEARCH_DIRS"]

    @property
    def recipe_override_dirs(self) -> list[Path]:
        """Gets the list of recipe override directories."""
        return self._prefs["RECIPE_OVERRIDE_DIRS"]

    @property
    def github_token(self) -> str | None:
        """Gets the GitHub token, if set."""
        return self._prefs.get("GITHUB_TOKEN")

    @property
    def smb_url(self) -> str | None:
        """Gets the SMB URL, if set."""
        return self._prefs.get("SMB_URL")

    @property
    def smb_username(self) -> str | None:
        """Gets the SMB username, if set."""
        return self._prefs.get("SMB_USERNAME")

    @property
    def smb_password(self) -> str | None:
        """Gets the SMB password, if set."""
        return self._prefs.get("SMB_PASSWORD")

    @property
    def patch_url(self) -> str | None:
        """Gets the PATCH URL, if set."""
        return self._prefs.get("PATCH_URL")

    @property
    def patch_token(self) -> str | None:
        """Gets the PATCH token, if set."""
        return self._prefs.get("PATCH_TOKEN")

    @property
    def title_url(self) -> str | None:
        """Gets the TITLE URL, if set."""
        return self._prefs.get("TITLE_URL")

    @property
    def title_user(self) -> str | None:
        """Gets the TITLE username, if set."""
        return self._prefs.get("TITLE_USER")

    @property
    def title_pass(self) -> str | None:
        """Gets the TITLE password, if set."""
        return self._prefs.get("TITLE_PASS")

    @property
    def jc_api(self) -> str | None:
        """Gets the JumpCloud API URL, if set."""
        return self._prefs.get("JC_API")

    @property
    def jc_org(self) -> str | None:
        """Gets the JumpCloud organization ID, if set."""
        return self._prefs.get("JC_ORG")

    @property
    def fw_server_host(self) -> str | None:
        """Gets the FileWave server host, if set."""
        return self._prefs.get("FW_SERVER_HOST")

    @property
    def fw_server_port(self) -> str | None:
        """Gets the FileWave server port, if set."""
        return self._prefs.get("FW_SERVER_PORT")

    @property
    def fw_admin_user(self) -> str | None:
        """Gets the FileWave admin username, if set."""
        return self._prefs.get("FW_ADMIN_USER")

    @property
    def fw_admin_password(self) -> str | None:
        """Gets the FileWave admin password, if set."""
        return self._prefs.get("FW_ADMIN_PASSWORD")

    @property
    def bes_root_server(self) -> str | None:
        """Gets the BigFix root server, if set."""
        return self._prefs.get("BES_ROOT_SERVER")

    @property
    def bes_username(self) -> str | None:
        """Gets the BigFix username, if set."""
        return self._prefs.get("BES_USERNAME")

    @property
    def bes_password(self) -> str | None:
        """Gets the BigFix password, if set."""
        return self._prefs.get("BES_PASSWORD")

    @property
    def client_id(self) -> str | None:
        """Gets the Intune client ID, if set."""
        return self._prefs.get("CLIENT_ID")

    @property
    def client_secret(self) -> str | None:
        """Gets the Intune client secret, if set."""
        return self._prefs.get("CLIENT_SECRET")

    @property
    def tenant_id(self) -> str | None:
        """Gets the Intune tenant ID, if set."""
        return self._prefs.get("TENANT_ID")

    @property
    def virustotal_api_key(self) -> str | None:
        """Gets the VirusTotal API key, if set."""
        return self._prefs.get("VIRUSTOTAL_API_KEY")

    @property
    def fail_recipes_without_trust_info(self) -> bool | None:
        """Gets the flag indicating whether to fail recipes without trust info."""
        return self._prefs.get("FAIL_RECIPES_WITHOUT_TRUST_INFO")

    @property
    def stop_if_no_jss_upload(self) -> bool | None:
        """Gets the flag indicating whether to stop if no JSS upload occurs."""
        return self._prefs.get("STOP_IF_NO_JSS_UPLOAD")

    @property
    def cloud_dp(self) -> bool | None:
        """Gets the cloud distribution point setting."""
        return self._prefs.get("CLOUD_DP")

    @property
    def smb_shares(self) -> list[dict[str, str]] | None:
        """Gets the SMB shares configuration, if set."""
        return self._prefs.get("SMB_SHARES")
