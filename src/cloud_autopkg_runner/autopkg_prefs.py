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

import asyncio
import json
import plistlib
import tempfile
from pathlib import Path
from typing import Any

from cloud_autopkg_runner import logging_config
from cloud_autopkg_runner.exceptions import (
    InvalidFileContents,
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

    _instance: "AutoPkgPrefs | None" = None
    _DEFAULT_PREF_FILE_PATH = Path(
        "~/Library/Preferences/com.github.autopkg.plist"
    ).expanduser()

    def __new__(cls, file_path: Path = _DEFAULT_PREF_FILE_PATH) -> "AutoPkgPrefs":
        """Create a new instance of AutoPkgPrefs if one doesn't exist.

        This `__new__` method implements the Singleton pattern, ensuring
        that only one instance of the `AutoPkgPrefs` class is ever created.
        If an instance already exists, it is returned; otherwise, a new
        instance is created and stored for future use.

        Args:
            file_path: The path to the preference file. Defaults to
                `~/Library/Preferences/com.github.autopkg.plist`. This file can be in
                JSON or Plist format. This argument is only used on the
                initial creation of the singleton instance.

        Returns:
            The AutoPkgPrefs instance.
        """
        if not cls._instance:
            cls._instance = super().__new__(cls)
            cls._instance.initializer(file_path)
        return cls._instance

    def __init__(self, file_path: Path = _DEFAULT_PREF_FILE_PATH) -> None:
        """Creates an AutoPkgPrefs object from a plist file.

        Loads the contents of the plist file, separates the known preferences
        from the extra preferences, and creates a new
        AutoPkgPrefs object.

        Args:
            file_path: The path to the preference file. Defaults to
                `~/Library/Preferences/com.github.autopkg.plist`. This file can be in
                JSON or Plist format.
        """
        if hasattr(self, "_initialized"):
            return  # Prevent re-initialization

        self.initializer(file_path)

    def initializer(self, file_path: Path) -> None:
        """Creates an AutoPkgPrefs object from a plist file.

        Loads the contents of the plist file, separates the known preferences
        from the extra preferences, and creates a new
        AutoPkgPrefs object.

        Args:
            file_path: The path to the preference file. This file can be in
                JSON or Plist format.
        """
        self._prefs: dict[str, Any] = (
            self._default_preferences()
            | self._normalize_preference_values(
                self._get_preference_file_contents(file_path)
            )
        )

        self._initialized = True

    @staticmethod
    def _convert_to_path(string: str) -> Path:
        """Converts a string to a Path object.

        Converts a string into a Path object that is expanded to include the user's home
        directory.

        Args:
            string: A string representing a single path.

        Returns:
            A Path object representing the expanded path.
        """
        return Path(string).expanduser()

    @staticmethod
    def _convert_to_list_of_paths(value: str | list[str]) -> list[Path]:
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
        paths = [value] if isinstance(value, str) else value
        return [Path(p).expanduser() for p in paths]

    @staticmethod
    def _default_preferences() -> dict[str, Path | list[Path]]:
        """Provides a dictionary of default AutoPkg preferences.

        These defaults are used if no preference file is found or if specific
        preferences are not defined in the loaded file. Paths are
        automatically expanded to include the user's home directory.

        Returns:
            A dictionary containing default AutoPkg preference keys and their
            corresponding Path or list of Path values.
        """
        return {
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

    @staticmethod
    def _get_preference_file_contents(file_path: Path) -> dict[str, Any]:
        """Reads and parses the contents of the AutoPkg preference file.

        Attempts to read the preference file from the specified path. If no path
        is provided, it defaults to `~/Library/Preferences/com.github.autopkg.plist`.
        The file is first attempted to be parsed as JSON, and if that fails,
        as a macOS plist.

        Args:
            file_path: The path to the preference file.

        Returns:
            A dictionary representing the parsed preferences from the file.

        Raises:
            PreferenceFileNotFoundError: If the specified `file_path` does not exist.
            InvalidFileContents: If the file exists but cannot be parsed as
                either JSON or a plist.
        """
        try:
            file_contents = file_path.read_bytes()
        except FileNotFoundError as exc:
            raise PreferenceFileNotFoundError(file_path) from exc

        prefs: dict[str, Any] = {}
        try:
            prefs = json.loads(file_contents.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            try:
                prefs = plistlib.loads(file_contents)
            except plistlib.InvalidFileException as exc:
                raise InvalidFileContents(file_path) from exc

        return prefs

    def _normalize_preference_values(
        self, preferences: dict[str, Any]
    ) -> dict[str, Any]:
        """Normalizes certain preference values to appropriate Python types.

        Specifically, converts string representations of paths to `pathlib.Path` objects
        and lists of string paths to lists of `pathlib.Path` objects.

        Args:
            preferences: A dictionary of preferences to normalize.

        Returns:
            A new dictionary with specified preference values converted to
            their appropriate types.
        """
        if "CACHE_DIR" in preferences:
            preferences["CACHE_DIR"] = self._convert_to_path(preferences["CACHE_DIR"])
        if "RECIPE_REPO_DIR" in preferences:
            preferences["RECIPE_REPO_DIR"] = self._convert_to_path(
                preferences["RECIPE_REPO_DIR"]
            )
        if "MUNKI_REPO" in preferences:
            preferences["MUNKI_REPO"] = self._convert_to_path(preferences["MUNKI_REPO"])

        if "RECIPE_SEARCH_DIRS" in preferences:
            preferences["RECIPE_SEARCH_DIRS"] = self._convert_to_list_of_paths(
                preferences["RECIPE_SEARCH_DIRS"]
            )
        if "RECIPE_OVERRIDE_DIRS" in preferences:
            preferences["RECIPE_OVERRIDE_DIRS"] = self._convert_to_list_of_paths(
                preferences["RECIPE_OVERRIDE_DIRS"]
            )

        return preferences

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

    def to_json(self, indent: int | None = None) -> str:
        """Serializes the preferences to a JSON-formatted string.

        Converts all Path objects and lists of Path objects to strings.

        Args:
            indent: Number of spaces for indentation in the output JSON.
                    If None, the JSON will be compact.

        Returns:
            A JSON string representation of the preferences.
        """

        def _serialize(
            *,
            value: str | int | float | bool | Path | list[Any] | dict[str, Any] | None,
        ) -> str | int | float | bool | None | list[Any] | dict[str, Any]:
            if isinstance(value, Path):
                return str(value)
            if isinstance(value, list):
                # Recursively apply serialize to each item in the list
                return [_serialize(value=item) for item in value]
            if isinstance(value, dict):
                # Recursively apply serialize to each value in the dictionary
                return {k: _serialize(value=v) for k, v in value.items()}
            # For all other types (str, int, bool, None, etc.), return as is
            return value

        serializable_prefs = {
            key: _serialize(value=value) for key, value in self._prefs.items()
        }
        return json.dumps(serializable_prefs, indent=indent)

    async def to_json_file(self, indent: int | None = None) -> Path:
        """Serializes the preferences to a temporary JSON file.

        This method generates a JSON string representation of the preferences
        (converting Path objects to strings) and then asynchronously writes
        this string to a temporary file. The file is created with a unique name
        and is configured to *not* be deleted automatically upon closure of its
        file object, allowing it to persist for external processes.

        It uses `asyncio.to_thread` to offload the blocking file writing
        operation to a separate thread, preventing the main event loop from
        being blocked.

        The path to the created temporary file is stored in `_temp_pref_file_path`.
        It is the responsibility of the caller (or the application's lifecycle
        management) to eventually call `cleanup_temp_file()` to delete this file.

        Args:
            indent: Number of spaces for indentation in the output JSON.
                    If None, the JSON will be compact.

        Returns:
            The Path object pointing to the created temporary JSON file.
        """

        def _write_and_get_path(data: str) -> Path:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, encoding="utf-8"
            ) as tmp:
                tmp.write(data)
            return Path(tmp.name)

        # Offload the file write operation to a separate thread
        self._temp_json_file_path = await asyncio.to_thread(
            _write_and_get_path, self.to_json(indent)
        )

        return self._temp_json_file_path

    def cleanup_temp_file(self) -> None:
        """Cleans up (deletes) the temporary preference file if it exists.

        This method should be called explicitly when the temporary preferences
        file is no longer needed by external processes. It checks if a temporary
        file path has been stored and, if so, attempts to delete the file.
        Errors during deletion (e.g., file not found, permission denied) are caught
        and logged, preventing the application from crashing.
        """
        if self._temp_json_file_path:
            if self._temp_json_file_path.exists():
                try:
                    self._temp_json_file_path.unlink()
                except OSError as exc:
                    logger = logging_config.get_logger(__name__)
                    logger.warning(
                        "Could not delete temporary prefs file %s: %s",
                        self._temp_json_file_path,
                        exc,
                    )
            self._temp_json_file_path = None

    def __del__(self) -> None:
        """Attempts to clean up the temporary preference file during garbage collection.

        This method is a fallback for cleanup. It calls `cleanup_temp_file()`.
        However, relying solely on `__del__` for critical resource management
        (like file deletion) is generally discouraged in Python due to
        unpredictable execution times and potential issues during program shutdown.
        It is highly recommended to call `cleanup_temp_file()` explicitly.
        """
        self.cleanup_temp_file()

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
