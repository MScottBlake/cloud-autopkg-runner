"""Module for managing AutoPkg preferences in cloud-autopkg-runner.

This module provides the `AutoPkgPrefs` class, which encapsulates
the logic for loading, accessing, and managing AutoPkg preferences.

The `AutoPkgPrefs` class supports type-safe access to well-known AutoPkg
preference keys, while also allowing access to arbitrary preferences
defined in the plist file. It handles the conversion of preference
values to the appropriate Python types (e.g., strings to Paths).

The `AutoPkgPrefs` class offers a hybrid interface:
- Attribute-based access: For well-known, type-safe preferences,
  using Pythonic `snake_case` names. Each property has an explicit getter and setter
  that handles type conversions (e.g., str to Path). This ensures strong static
  type checking.
- Method-based access (get()/set()): For all preferences, including arbitrary
  ones not explicitly defined as properties, using their original, usually
  `UPPERCASE_KEY` names. These methods provide direct access to the raw (string or
  primitive) stored values and the ability to specify default values.
"""

import asyncio
import copy
import json
import plistlib
import tempfile
from pathlib import Path
from types import TracebackType
from typing import Any

from cloud_autopkg_runner import logging_config
from cloud_autopkg_runner.exceptions import (
    InvalidFileContents,
    PreferenceFileNotFoundError,
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
# - https://github.com/autopkg/fleet-recipes


class AutoPkgPrefs:
    """Manages AutoPkg preferences loaded from a plist file.

    Provides a hybrid interface for accessing and modifying preferences:
    attribute-based for known, type-safe preferences, and method-based (get/set)
    for all preferences including arbitrary ones.
    """

    _temp_json_file_path: Path | None = None
    _DEFAULT_PREF_FILE_PATH = Path(
        "~/Library/Preferences/com.github.autopkg.plist"
    ).expanduser()

    def __init__(self, file_path: Path = _DEFAULT_PREF_FILE_PATH) -> None:
        """Loads the contents of `file_path` and initializes preferences.

        The `_prefs` dictionary is populated with default preferences in their raw
        string/primitive format. Any preferences loaded from `file_path` will then
        override or add to these defaults.

        Args:
            file_path: The path to the preference file. Defaults to
                `~/Library/Preferences/com.github.autopkg.plist`. This file can be in
                JSON or Plist format.
        """
        self._prefs: dict[str, Any] = self._get_default_preferences()

        file_contents = self._get_preference_file_contents(file_path)
        self._prefs.update(file_contents)

    def __enter__(self) -> "AutoPkgPrefs":
        """Enter the runtime context related to this object.

        Returns:
            The AutoPkgPrefs instance itself.
        """
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        """Exit the runtime context and clean up temporary files.

        This method always attempts to delete the temporary JSON file created by
        `to_json_file()` when leaving a context block, regardless of whether an
        exception occurred. Exceptions raised inside the context are not
        suppressed and will propagate after cleanup.
        """
        self.cleanup_temp_file()

    def __del__(self) -> None:
        """Destructor that attempts to clean up temporary files.

        Calls `cleanup_temp_file()` to remove any temporary JSON file created.
        This is a best-effort cleanup mechanism; relying on `__del__` alone
        for resource management is discouraged because it may not run
        predictably during interpreter shutdown. Explicit calls to
        `cleanup_temp_file()` are strongly recommended.
        """
        self.cleanup_temp_file()

    def __repr__(self) -> str:
        """Return a string representation of the AutoPkgPrefs object for debugging.

        Sensitive values such as passwords and tokens are redacted in the output
        to prevent accidental exposure in logs or console output.

        Returns:
            str: A string showing the class name and a preview of preference keys
            and values, with sensitive values replaced by "<redacted>".
        """
        redaction_keywords = {"pass", "token", "secret"}
        redacted_keys: set[str] = {
            key
            for key in self._prefs
            if any(keyword in key.lower() for keyword in redaction_keywords)
        }
        prefs_preview = {
            k: ("<redacted>" if k in redacted_keys else v)
            for k, v in self._prefs.items()
        }
        return f"{self.__class__.__name__}({prefs_preview})"

    def __deepcopy__(self, memo: dict[int, "AutoPkgPrefs"]) -> "AutoPkgPrefs":
        """Create a deep copy of an `AutoPkgPrefs` instance.

        This method customizes the deep copy behavior to ensure that the
        `_temp_json_file_path` attribute is set to `None` in the copied object,
        preventing issues with concurrency. All other attributes are deep copied
        as usual.

        Args:
            memo: A dictionary of objects already copied during the current
                deep copy operation. This is used to prevent infinite recursion
                for circularly referenced objects.

        Returns:
            A new `AutoPkgPrefs` instance that is a deep copy of the original,
            with `_temp_json_file_path` set to `None`.
        """
        cls = self.__class__
        obj = cls.__new__(cls)
        memo[id(self)] = obj  # Register the new object in the memo

        # Copy all attributes except `_temp_json_file_path`
        for k, v in self.__dict__.items():
            if k != "_temp_json_file_path":
                setattr(obj, k, copy.deepcopy(v, memo))
            else:
                # _temp_json_file_path = None
                setattr(obj, k, None)

        return obj

    @staticmethod
    def _get_default_preferences() -> dict[str, Any]:
        """Provides a dictionary of default AutoPkg preferences.

        These preferences will always be present in `_prefs` and thus in the
        JSON output unless explicitly unset (if applicable). Other preferences
        will only be present in `_prefs` if loaded from the file or explicitly
        set.

        Returns:
            A dictionary containing default AutoPkg preference keys
            and their corresponding raw values.
        """
        return {
            "CACHE_DIR": "~/Library/AutoPkg/Cache",
            "RECIPE_SEARCH_DIRS": [
                ".",
                "~/Library/AutoPkg/Recipes",
                "/Library/AutoPkg/Recipes",
            ],
            "RECIPE_OVERRIDE_DIRS": ["~/Library/AutoPkg/RecipeOverrides"],
            "RECIPE_REPO_DIR": "~/Library/AutoPkg/RecipeRepos",
        }

    @staticmethod
    def _get_preference_file_contents(file_path: Path) -> dict[str, Any]:
        """Reads and parses the contents of the AutoPkg preference file.

        Attempts to read and parse the specified file first as JSON, then as a
        macOS plist if JSON decoding fails. Only if both formats fail will an
        `InvalidFileContents` exception be raised.

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

    def get(self, key: str, default: object = None) -> object:
        """Retrieves the value of a preference by key.

        Args:
            key (str): The name of the preference to retrieve.
            default (object, optional): The value to return if the key is not found.
                Defaults to None.

        Returns:
            object: The preference value if found, otherwise the provided default.
        """
        return self._prefs.get(key, default)

    def set(self, key: str, value: object) -> None:
        """Stores a preference value by its uppercase key.

        This method assigns the raw `value` directly to the internal dictionary
        without performing type conversion (e.g., Path → str). For well-known
        preferences with dedicated property setters, prefer using those setters
        to ensure correct internal storage format.

        Args:
            key (str): The uppercase name of the preference to set.
            value (object): The value to assign to the preference.
        """
        self._prefs[key] = value

    def clone(self) -> "AutoPkgPrefs":
        """Create a fully independent deep copy of this AutoPkgPrefs instance.

        This method utilizes `copy.deepcopy()` to produce a new instance of
        `AutoPkgPrefs`. The clone will have its own independent mutable state,
        such as the internal preferences dictionary (`_prefs`), ensuring that
        modifications to the clone do not affect the original object.

        This is particularly useful in concurrent environments or when managing
        isolated "git worktrees" where each operation needs to start with a
        pristine or distinct set of settings.

        Returns:
            AutoPkgPrefs: A new, independent `AutoPkgPrefs` instance containing a
                deep copy of all mutable preferences.
        """
        return copy.deepcopy(self)

    def to_json(self, indent: int | None = None) -> str:
        """Serializes the preferences to a JSON-formatted string.

        This method serializes only the preferences present in the `_prefs` dictionary.
        Keys that were never present will not appear in the output.

        Args:
            indent: Number of spaces for indentation in the output JSON.
                If None, the JSON will be compact.

        Returns:
            A JSON string representation of the preferences.
        """
        return json.dumps(self._prefs, indent=indent)

    async def to_json_file(self, indent: int | None = None) -> Path:
        """Write or reuse a temporary JSON file for the current preferences.

        This asynchronous method serializes the in-memory AutoPkg preferences
        to a temporary JSON file on disk. If a temporary file has not yet been
        created or if the existing file has been removed, it creates a new one.
        Otherwise, it reuses the existing file path to avoid generating
        redundant temporary files.

        The write operation is executed in a background thread using
        `asyncio.to_thread` to prevent blocking the event loop. The resulting
        file path is stored in `self._temp_json_file_path`.

        Args:
            indent: Optional number of spaces to use for indentation in the output
                JSON. If omitted or `None`, the JSON will be compact.

        Returns:
            Path: The path to the existing or newly created temporary JSON file.
        """

        def _write_and_get_path(data: str) -> Path:
            """Synchronously writes data to a temporary file and returns its path."""
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, encoding="utf-8"
            ) as tmp:
                tmp.write(data)
            return Path(tmp.name)

        if not self._temp_json_file_path or not self._temp_json_file_path.exists():
            self._temp_json_file_path = await asyncio.to_thread(
                _write_and_get_path, self.to_json(indent)
            )

        return self._temp_json_file_path

    def cleanup_temp_file(self) -> None:
        """Deletes the temporary preference file if it exists.

        This method performs a best-effort cleanup of any temporary JSON file
        previously created by `to_json_file()`. It is safe to call multiple times;
        if no temporary file exists, it performs no action. The cleanup step is
        typically triggered when stored preferences change or when exiting a
        context block.
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

    @staticmethod
    def _convert_to_list_of_paths(
        value: str | list[str] | Path | list[Path],
    ) -> list[Path]:
        """Converts string(s) or Path(s) to a list of expanded Path objects.

        If the input is a string or Path, it is treated as a single path
        and converted into a list containing that path. If the input is
        already a list of strings or Paths, each item is converted into
        a Path object. All paths are expanded to include the user's home
        directory.

        Args:
            value: A string, Path, list of strings, or list of Paths
                representing paths.

        Returns:
            A list of Path objects, where each Path object represents a
            path from the input.
        """
        paths = [value] if not isinstance(value, list) else value
        return [Path(p).expanduser() for p in paths]

    # --- Internal preference helper methods ---

    def _get_path_pref(self, key: str) -> Path:
        """Retrieves a path preference and converts it to a Path object.

        Args:
            key: The name of the preference key to retrieve.

        Returns:
            A Path object representing the stored preference value.
        """
        return Path(self._prefs[key]).expanduser()

    def _set_path_pref(self, key: str, value: str | Path) -> None:
        """Stores a path preference as a string.

        This method updates the stored value only if it differs from the
        existing one. When a change is detected, any previously generated
        temporary JSON file is deleted to ensure future serialization
        reflects the updated data.

        Args:
            key: The name of the preference key to set.
            value: The path to store. Accepts a string or Path object.
        """
        self._prefs[key] = str(value)
        self.cleanup_temp_file()

    def _get_list_of_paths_pref(self, key: str) -> list[Path]:
        """Retrieves a list-of-paths preference and converts it to Path objects.

        Args:
            key: The name of the preference key to retrieve.

        Returns:
            A list of Path objects representing the stored preference values.
        """
        return self._convert_to_list_of_paths(self._prefs[key])

    def _set_list_of_paths_pref(
        self, key: str, value: str | Path | list[str] | list[Path]
    ) -> None:
        """Stores a list-of-paths preference as a list of strings.

        Updates are applied only when the new value differs from the stored one.
        When updated, any previously generated temporary JSON file is deleted
        so that subsequent AutoPkg operations use the refreshed data.

        Args:
            key: The name of the preference key to set.
            value: The path(s) to store. May be a single string/Path
                or a list of strings/Paths.
        """
        self._prefs[key] = [str(p) for p in self._convert_to_list_of_paths(value)]
        self.cleanup_temp_file()

    def _get_str_pref(self, key: str) -> str | None:
        """Retrieves a string preference.

        Args:
            key: The name of the preference key to retrieve.

        Returns:
            The stored string value, or None if not set.
        """
        return self._prefs.get(key)

    def _set_str_pref(self, key: str, value: str | None) -> None:
        """Stores a string preference.

        If the new value differs from the existing one, the preference is
        updated and any previously generated temporary JSON file is deleted.
        This ensures that serialized data remains consistent with in-memory
        state.

        Args:
            key: The name of the preference key to set.
            value: The string value to store, or None to unset.
        """
        self._prefs[key] = value
        self.cleanup_temp_file()

    def _get_bool_pref(self, key: str, *, default: bool = False) -> bool:
        """Retrieves a boolean preference, interpreting common string values.

        Args:
            key: The name of the preference key to retrieve.
            default: The value to return if the key is not set.

        Returns:
            A boolean value. If the stored value is a string, it is interpreted
            as True if it matches {"1", "true", "yes"} (case-insensitive).
        """
        raw = self._prefs.get(key, default)
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            return raw.lower() in {"1", "true", "yes"}
        return bool(raw)

    def _set_bool_pref(self, key: str, *, value: bool) -> None:
        """Stores a boolean preference.

        The preference is updated only if the new boolean value differs from
        the current one. When changed, any existing temporary JSON file is
        deleted to ensure future serialization reflects the new value.

        Args:
            key: The name of the preference key to set.
            value: The boolean value to store.
        """
        self._prefs[key] = bool(value)
        self.cleanup_temp_file()

    # --- Path preferences (always exist thanks to _get_default_preferences) ---

    @property
    def cache_dir(self) -> Path:
        """Gets the cache directory path.

        Returns:
            A Path object representing the cache directory.
        """
        return self._get_path_pref("CACHE_DIR")

    @cache_dir.setter
    def cache_dir(self, value: str | Path) -> None:
        """Sets the cache directory path.

        Args:
            value: The new cache directory path as a string or Path.
        """
        self._set_path_pref("CACHE_DIR", value)

    @property
    def recipe_repo_dir(self) -> Path:
        """Gets the recipe repository directory path.

        Returns:
            A Path object representing the recipe repository directory.
        """
        return self._get_path_pref("RECIPE_REPO_DIR")

    @recipe_repo_dir.setter
    def recipe_repo_dir(self, value: str | Path) -> None:
        """Sets the recipe repository directory path.

        Args:
            value: The new recipe repository path as a string or Path.
        """
        self._set_path_pref("RECIPE_REPO_DIR", value)

    @property
    def recipe_search_dirs(self) -> list[Path]:
        """Gets the list of recipe search directories.

        Returns:
            A list of Path objects representing recipe search directories.
        """
        return self._get_list_of_paths_pref("RECIPE_SEARCH_DIRS")

    @recipe_search_dirs.setter
    def recipe_search_dirs(self, value: str | Path | list[str] | list[Path]) -> None:
        """Sets the list of recipe search directories.

        Args:
            value: A string, Path, or a list of strings/Paths representing
                the directories to search.
        """
        self._set_list_of_paths_pref("RECIPE_SEARCH_DIRS", value)

    @property
    def recipe_override_dirs(self) -> list[Path]:
        """Gets the list of recipe override directories.

        Returns:
            A list of Path objects representing recipe override directories.
        """
        return self._get_list_of_paths_pref("RECIPE_OVERRIDE_DIRS")

    @recipe_override_dirs.setter
    def recipe_override_dirs(self, value: str | Path | list[str] | list[Path]) -> None:
        """Sets the list of recipe override directories.

        Args:
            value: A string, Path, or a list of strings/Paths representing
                the override directories.
        """
        self._set_list_of_paths_pref("RECIPE_OVERRIDE_DIRS", value)

    # --- Path preferences (optional) ---

    @property
    def munki_repo(self) -> Path | None:
        """Gets the Munki repository path if set.

        Returns:
            Path | None: The Munki repository path as a Path object,
            or None if not set.
        """
        val = self._prefs.get("MUNKI_REPO")
        return Path(val).expanduser() if val else None

    @munki_repo.setter
    def munki_repo(self, value: str | Path | None) -> None:
        """Sets the Munki repository path.

        Args:
            value: The new Munki repository path as a string or Path.
                If None, the preference is unset.
        """
        self._prefs["MUNKI_REPO"] = str(value) if value else None

    # --- String preferences (optional) ---

    @property
    def github_token(self) -> str | None:
        """Retrieves the GitHub token preference.

        Returns:
            str | None: The GitHub token, or None if unset.
        """
        return self._get_str_pref("GITHUB_TOKEN")

    @github_token.setter
    def github_token(self, value: str | None) -> None:
        """Sets the GitHub token preference.

        Args:
            value: The GitHub token string, or None to unset.
        """
        self._set_str_pref("GITHUB_TOKEN", value)

    @property
    def smb_url(self) -> str | None:
        """Retrieves the SMB URL preference.

        Returns:
            str | None: The SMB URL, or None if unset.
        """
        return self._get_str_pref("SMB_URL")

    @smb_url.setter
    def smb_url(self, value: str | None) -> None:
        """Sets the SMB URL preference.

        Args:
            value: The SMB URL string, or None to unset.
        """
        self._set_str_pref("SMB_URL", value)

    @property
    def smb_username(self) -> str | None:
        """Retrieves the SMB username preference.

        Returns:
            str | None: The SMB username, or None if unset.
        """
        return self._get_str_pref("SMB_USERNAME")

    @smb_username.setter
    def smb_username(self, value: str | None) -> None:
        """Sets the SMB username preference.

        Args:
            value: The SMB username string, or None to unset.
        """
        self._set_str_pref("SMB_USERNAME", value)

    @property
    def smb_password(self) -> str | None:
        """Retrieves the SMB password preference.

        Returns:
            str | None: The SMB password, or None if unset.
        """
        return self._get_str_pref("SMB_PASSWORD")

    @smb_password.setter
    def smb_password(self, value: str | None) -> None:
        """Sets the SMB password preference.

        Args:
            value: The SMB password string, or None to unset.
        """
        self._set_str_pref("SMB_PASSWORD", value)

    @property
    def patch_url(self) -> str | None:
        """Retrieves the PATCH URL preference.

        Returns:
            str | None: The PATCH URL, or None if unset.
        """
        return self._get_str_pref("PATCH_URL")

    @patch_url.setter
    def patch_url(self, value: str | None) -> None:
        """Sets the PATCH URL preference.

        Args:
            value: The PATCH URL string, or None to unset.
        """
        self._set_str_pref("PATCH_URL", value)

    @property
    def patch_token(self) -> str | None:
        """Retrieves the PATCH token preference.

        Returns:
            str | None: The PATCH token, or None if unset.
        """
        return self._get_str_pref("PATCH_TOKEN")

    @patch_token.setter
    def patch_token(self, value: str | None) -> None:
        """Sets the PATCH token preference.

        Args:
            value: The PATCH token string, or None to unset.
        """
        self._set_str_pref("PATCH_TOKEN", value)

    @property
    def title_url(self) -> str | None:
        """Retrieves the TITLE URL preference.

        Returns:
            str | None: The TITLE URL, or None if unset.
        """
        return self._get_str_pref("TITLE_URL")

    @title_url.setter
    def title_url(self, value: str | None) -> None:
        """Sets the TITLE URL preference.

        Args:
            value: The TITLE URL string, or None to unset.
        """
        self._set_str_pref("TITLE_URL", value)

    @property
    def title_user(self) -> str | None:
        """Retrieves the TITLE username preference.

        Returns:
            str | None: The TITLE username, or None if unset.
        """
        return self._get_str_pref("TITLE_USER")

    @title_user.setter
    def title_user(self, value: str | None) -> None:
        """Sets the TITLE username preference.

        Args:
            value: The TITLE username string, or None to unset.
        """
        self._set_str_pref("TITLE_USER", value)

    @property
    def title_pass(self) -> str | None:
        """Retrieves the TITLE password preference.

        Returns:
            str | None: The TITLE password, or None if unset.
        """
        return self._get_str_pref("TITLE_PASS")

    @title_pass.setter
    def title_pass(self, value: str | None) -> None:
        """Sets the TITLE password preference.

        Args:
            value: The TITLE password string, or None to unset.
        """
        self._set_str_pref("TITLE_PASS", value)

    @property
    def jc_api(self) -> str | None:
        """Retrieves the JumpCloud API URL preference.

        Returns:
            str | None: The JumpCloud API URL, or None if unset.
        """
        return self._get_str_pref("JC_API")

    @jc_api.setter
    def jc_api(self, value: str | None) -> None:
        """Sets the JumpCloud API URL preference.

        Args:
            value: The JumpCloud API URL string, or None to unset.
        """
        self._set_str_pref("JC_API", value)

    @property
    def jc_org(self) -> str | None:
        """Retrieves the JumpCloud organization ID preference.

        Returns:
            str | None: The JumpCloud organization ID, or None if unset.
        """
        return self._get_str_pref("JC_ORG")

    @jc_org.setter
    def jc_org(self, value: str | None) -> None:
        """Sets the JumpCloud organization ID preference.

        Args:
            value: The JumpCloud organization ID string, or None to unset.
        """
        self._set_str_pref("JC_ORG", value)

    @property
    def fw_server_host(self) -> str | None:
        """Retrieves the FileWave server host preference.

        Returns:
            str | None: The FileWave server host, or None if unset.
        """
        return self._get_str_pref("FW_SERVER_HOST")

    @fw_server_host.setter
    def fw_server_host(self, value: str | None) -> None:
        """Sets the FileWave server host preference.

        Args:
            value: The FileWave server host string, or None to unset.
        """
        self._set_str_pref("FW_SERVER_HOST", value)

    @property
    def fw_server_port(self) -> str | None:
        """Retrieves the FileWave server port preference.

        Returns:
            str | None: The FileWave server port, or None if unset.
        """
        return self._get_str_pref("FW_SERVER_PORT")

    @fw_server_port.setter
    def fw_server_port(self, value: str | None) -> None:
        """Sets the FileWave server port preference.

        Args:
            value: The FileWave server port string, or None to unset.
        """
        self._set_str_pref("FW_SERVER_PORT", value)

    @property
    def fw_admin_user(self) -> str | None:
        """Retrieves the FileWave admin username preference.

        Returns:
            str | None: The FileWave admin username, or None if unset.
        """
        return self._get_str_pref("FW_ADMIN_USER")

    @fw_admin_user.setter
    def fw_admin_user(self, value: str | None) -> None:
        """Sets the FileWave admin username preference.

        Args:
            value: The FileWave admin username string, or None to unset.
        """
        self._set_str_pref("FW_ADMIN_USER", value)

    @property
    def fw_admin_password(self) -> str | None:
        """Retrieves the FileWave admin password preference.

        Returns:
            str | None: The FileWave admin password, or None if unset.
        """
        return self._get_str_pref("FW_ADMIN_PASSWORD")

    @fw_admin_password.setter
    def fw_admin_password(self, value: str | None) -> None:
        """Sets the FileWave admin password preference.

        Args:
            value: The FileWave admin password string, or None to unset.
        """
        self._set_str_pref("FW_ADMIN_PASSWORD", value)

    @property
    def bes_root_server(self) -> str | None:
        """Retrieves the BigFix root server preference.

        Returns:
            str | None: The BigFix root server, or None if unset.
        """
        return self._get_str_pref("BES_ROOT_SERVER")

    @bes_root_server.setter
    def bes_root_server(self, value: str | None) -> None:
        """Sets the BigFix root server preference.

        Args:
            value: The BigFix root server string, or None to unset.
        """
        self._set_str_pref("BES_ROOT_SERVER", value)

    @property
    def bes_username(self) -> str | None:
        """Retrieves the BigFix username preference.

        Returns:
            str | None: The BigFix username, or None if unset.
        """
        return self._get_str_pref("BES_USERNAME")

    @bes_username.setter
    def bes_username(self, value: str | None) -> None:
        """Sets the BigFix username preference.

        Args:
            value: The BigFix username string, or None to unset.
        """
        self._set_str_pref("BES_USERNAME", value)

    @property
    def bes_password(self) -> str | None:
        """Retrieves the BigFix password preference.

        Returns:
            str | None: The BigFix password, or None if unset.
        """
        return self._get_str_pref("BES_PASSWORD")

    @bes_password.setter
    def bes_password(self, value: str | None) -> None:
        """Sets the BigFix password preference.

        Args:
            value: The BigFix password string, or None to unset.
        """
        self._set_str_pref("BES_PASSWORD", value)

    @property
    def client_id(self) -> str | None:
        """Retrieves the Intune client ID preference.

        Returns:
            str | None: The Intune client ID, or None if unset.
        """
        return self._get_str_pref("CLIENT_ID")

    @client_id.setter
    def client_id(self, value: str | None) -> None:
        """Sets the Intune client ID preference.

        Args:
            value: The Intune client ID string, or None to unset.
        """
        self._set_str_pref("CLIENT_ID", value)

    @property
    def client_secret(self) -> str | None:
        """Retrieves the Intune client secret preference.

        Returns:
            str | None: The Intune client secret, or None if unset.
        """
        return self._get_str_pref("CLIENT_SECRET")

    @client_secret.setter
    def client_secret(self, value: str | None) -> None:
        """Sets the Intune client secret preference.

        Args:
            value: The Intune client secret string, or None to unset.
        """
        self._set_str_pref("CLIENT_SECRET", value)

    @property
    def tenant_id(self) -> str | None:
        """Retrieves the Intune tenant ID preference.

        Returns:
            str | None: The Intune tenant ID, or None if unset.
        """
        return self._get_str_pref("TENANT_ID")

    @tenant_id.setter
    def tenant_id(self, value: str | None) -> None:
        """Sets the Intune tenant ID preference.

        Args:
            value: The Intune tenant ID string, or None to unset.
        """
        self._set_str_pref("TENANT_ID", value)

    @property
    def virustotal_api_key(self) -> str | None:
        """Retrieves the VirusTotal API key preference.

        Returns:
            str | None: The VirusTotal API key, or None if unset.
        """
        return self._get_str_pref("VIRUSTOTAL_API_KEY")

    @virustotal_api_key.setter
    def virustotal_api_key(self, value: str | None) -> None:
        """Sets the VirusTotal API key preference.

        Args:
            value: The VirusTotal API key string, or None to unset.
        """
        self._set_str_pref("VIRUSTOTAL_API_KEY", value)

    @property
    def fleet_api_base(self) -> str | None:
        """Retrieves the Fleet API Base URL preference.

        Returns:
            str | None: The Fleet API Base URL, or None if unset.
        """
        return self._get_str_pref("FLEET_API_BASE")

    @fleet_api_base.setter
    def fleet_api_base(self, value: str | None) -> None:
        """Sets the Fleet API Base URL preference.

        Args:
            value: The Fleet API Base URL string, or None to unset.
        """
        self._set_str_pref("FLEET_API_BASE", value)

    @property
    def fleet_api_token(self) -> str | None:
        """Retrieves the Fleet API Token preference.

        Returns:
            str | None: The Fleet API Token, or None if unset.
        """
        return self._get_str_pref("FLEET_API_TOKEN")

    @fleet_api_token.setter
    def fleet_api_token(self, value: str | None) -> None:
        """Sets the Fleet API Token preference.

        Args:
            value: The Fleet API Token string, or None to unset.
        """
        self._set_str_pref("FLEET_API_TOKEN", value)

    @property
    def fleet_team_id(self) -> str | None:
        """Retrieves the Fleet Team ID preference.

        Returns:
            str | None: The Fleet Team ID, or None if unset.
        """
        return self._get_str_pref("FLEET_TEAM_ID")

    @fleet_team_id.setter
    def fleet_team_id(self, value: str | None) -> None:
        """Sets the Fleet Team ID preference.

        Args:
            value: The Fleet Team ID string, or None to unset.
        """
        self._set_str_pref("FLEET_TEAM_ID", value)

    @property
    def aws_s3_bucket(self) -> str | None:
        """Retrieves the AWS S3 Bucket preference.

        Returns:
            str | None: The AWS S3 Bucket, or None if unset.
        """
        return self._get_str_pref("AWS_S3_BUCKET")

    @aws_s3_bucket.setter
    def aws_s3_bucket(self, value: str | None) -> None:
        """Sets the AWS S3 Bucket preference.

        Args:
            value: The AWS S3 Bucket string, or None to unset.
        """
        self._set_str_pref("AWS_S3_BUCKET", value)

    @property
    def aws_cloudfront_domain(self) -> str | None:
        """Retrieves the AWS CloudFront Domain preference.

        Returns:
            str | None: The AWS CloudFront Domain, or None if unset.
        """
        return self._get_str_pref("AWS_CLOUDFRONT_DOMAIN")

    @aws_cloudfront_domain.setter
    def aws_cloudfront_domain(self, value: str | None) -> None:
        """Sets the AWS CloudFront Domain preference.

        Args:
            value: The AWS CloudFront Domain string, or None to unset.
        """
        self._set_str_pref("AWS_CLOUDFRONT_DOMAIN", value)

    @property
    def aws_access_key_id(self) -> str | None:
        """Retrieves the AWS Access Key ID preference.

        Returns:
            str | None: The AWS Access Key ID, or None if unset.
        """
        return self._get_str_pref("AWS_ACCESS_KEY_ID")

    @aws_access_key_id.setter
    def aws_access_key_id(self, value: str | None) -> None:
        """Sets the AWS Access Key ID preference.

        Args:
            value: The AWS Access Key ID string, or None to unset.
        """
        self._set_str_pref("AWS_ACCESS_KEY_ID", value)

    @property
    def aws_secret_access_key(self) -> str | None:
        """Retrieves the AWS Secret Access Key preference.

        Returns:
            str | None: The AWS Secret Access Key, or None if unset.
        """
        return self._get_str_pref("AWS_SECRET_ACCESS_KEY")

    @aws_secret_access_key.setter
    def aws_secret_access_key(self, value: str | None) -> None:
        """Sets the AWS Secret Access Key preference.

        Args:
            value: The AWS Secret Access Key string, or None to unset.
        """
        self._set_str_pref("AWS_SECRET_ACCESS_KEY", value)

    @property
    def aws_default_region(self) -> str | None:
        """Retrieves the AWS Default Region preference.

        Returns:
            str | None: The AWS Default Region, or None if unset.
        """
        return self._get_str_pref("AWS_DEFAULT_REGION")

    @aws_default_region.setter
    def aws_default_region(self, value: str | None) -> None:
        """Sets the AWS Default Region preference.

        Args:
            value: The AWS Default Region string, or None to unset.
        """
        self._set_str_pref("AWS_DEFAULT_REGION", value)

    @property
    def fleet_gitops_repo_url(self) -> str | None:
        """Retrieves the Fleet GitOps Repo URL preference.

        Returns:
            str | None: The Fleet GitOps Repo URL, or None if unset.
        """
        return self._get_str_pref("FLEET_GITOPS_REPO_URL")

    @fleet_gitops_repo_url.setter
    def fleet_gitops_repo_url(self, value: str | None) -> None:
        """Sets the Fleet GitOps Repo URL preference.

        Args:
            value: The Fleet GitOps Repo URL string, or None to unset.
        """
        self._set_str_pref("FLEET_GITOPS_REPO_URL", value)

    @property
    def fleet_gitops_github_token(self) -> str | None:
        """Retrieves the Fleet GitOps GitHub Token preference.

        Returns:
            str | None: The Fleet GitOps GitHub Token, or None if unset.
        """
        return self._get_str_pref("FLEET_GITOPS_GITHUB_TOKEN")

    @fleet_gitops_github_token.setter
    def fleet_gitops_github_token(self, value: str | None) -> None:
        """Sets the Fleet GitOps GitHub Token preference.

        Args:
            value: The Fleet GitOps GitHub Token string, or None to unset.
        """
        self._set_str_pref("FLEET_GITOPS_GITHUB_TOKEN", value)

    @property
    def fleet_gitops_software_dir(self) -> str | None:
        """Retrieves the Fleet GitOps Software Directory preference.

        Returns:
            str | None: The Fleet GitOps Software Directory, or None if unset.
        """
        return self._get_str_pref("FLEET_GITOPS_SOFTWARE_DIR")

    @fleet_gitops_software_dir.setter
    def fleet_gitops_software_dir(self, value: str | None) -> None:
        """Sets the Fleet GitOps Software Directory preference.

        Args:
            value: The Fleet GitOps Software Directory string, or None to unset.
        """
        self._set_str_pref("FLEET_GITOPS_SOFTWARE_DIR", value)

    @property
    def fleet_gitops_team_yaml_path(self) -> str | None:
        """Retrieves the Fleet GitOps Team YAML Path preference.

        Returns:
            str | None: The Fleet GitOps Team YAML Path, or None if unset.
        """
        return self._get_str_pref("FLEET_GITOPS_TEAM_YAML_PATH")

    @fleet_gitops_team_yaml_path.setter
    def fleet_gitops_team_yaml_path(self, value: str | None) -> None:
        """Sets the Fleet GitOps Team YAML Path preference.

        Args:
            value: The Fleet GitOps Team YAML Path string, or None to unset.
        """
        self._set_str_pref("FLEET_GITOPS_TEAM_YAML_PATH", value)

    # --- Complex structured preferences ---

    @property
    def smb_shares(self) -> list[dict[str, str]] | None:
        """Retrieves the SMB shares configuration preference.

        Returns:
            list[dict[str, str]] | None: The SMB shares configuration,
            or None if unset.
        """
        return self._prefs.get("SMB_SHARES")

    @smb_shares.setter
    def smb_shares(self, value: list[dict[str, str]] | None) -> None:
        """Sets the SMB shares configuration preference.

        Args:
            value: A list of SMB share dictionaries, or None to unset.
        """
        self._prefs["SMB_SHARES"] = value

    # --- Boolean preferences ---

    @property
    def fail_recipes_without_trust_info(self) -> bool:
        """Retrieves whether the 'fail recipes without trust info' setting is enabled.

        Returns:
            bool: True if enabled, False otherwise.
        """
        return self._get_bool_pref("FAIL_RECIPES_WITHOUT_TRUST_INFO", default=False)

    @fail_recipes_without_trust_info.setter
    def fail_recipes_without_trust_info(self, value: bool) -> None:
        """Set the 'fail recipes without trust info' setting.

        Args:
            value: True to fail recipes missing trust info, False otherwise.
        """
        self._set_bool_pref("FAIL_RECIPES_WITHOUT_TRUST_INFO", value=value)

    @property
    def stop_if_no_jss_upload(self) -> bool:
        """Retrieves whether the 'stop if no JSS upload' setting is enabled.

        Returns:
            bool: True if enabled, False otherwise.
        """
        return self._get_bool_pref("STOP_IF_NO_JSS_UPLOAD", default=False)

    @stop_if_no_jss_upload.setter
    def stop_if_no_jss_upload(self, value: bool) -> None:
        """Set the 'stop if no JSS upload' setting.

        Args:
            value: True to stop when no JSS upload occurs, False otherwise.
        """
        self._set_bool_pref("STOP_IF_NO_JSS_UPLOAD", value=value)

    @property
    def cloud_dp(self) -> bool:
        """Retrieves whether the cloud distribution point is enabled.

        Returns:
            bool: True if enabled, False otherwise.
        """
        return self._get_bool_pref("CLOUD_DP", default=False)

    @cloud_dp.setter
    def cloud_dp(self, value: bool) -> None:
        """Set the cloud distribution point setting.

        Args:
            value: True to enable the cloud distribution point, False to disable.
        """
        self._set_bool_pref("CLOUD_DP", value=value)

    @property
    def gitops_mode(self) -> bool:
        """Retrieves whether the GitOps Mode is enabled.

        Returns:
            bool: True if enabled, False otherwise.
        """
        return self._get_bool_pref("GITOPS_MODE", default=False)

    @gitops_mode.setter
    def gitops_mode(self, value: bool) -> None:
        """Set the cloud GitOps Mode setting.

        Args:
            value: True to enable GitOps Mode, False to disable.
        """
        self._set_bool_pref("GITOPS_MODE", value=value)
