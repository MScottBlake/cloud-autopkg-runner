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
from typing import Any, Literal, TypeVar, overload

from cloud_autopkg_runner.exceptions import AutoPkgRunnerException, InvalidPlistContents

T = TypeVar("T")

# Overload key sources:
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
            raise AutoPkgRunnerException(f"Plist file not found: {plist_path}") from exc  # noqa: TRY003
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

    @overload
    def __getitem__(self, key: Literal["CACHE_DIR", "RECIPE_REPO_DIR"]) -> Path: ...

    @overload
    def __getitem__(self, key: Literal["MUNKI_REPO"]) -> Path | None: ...

    @overload
    def __getitem__(
        self, key: Literal["RECIPE_SEARCH_DIRS", "RECIPE_OVERRIDE_DIRS"]
    ) -> list[Path]: ...

    @overload
    def __getitem__(
        self,
        key: Literal[
            "GITHUB_TOKEN",
            "SMB_URL",
            "SMB_USERNAME",
            "SMB_PASSWORD",
            "PATCH_URL",
            "PATCH_TOKEN",
            "TITLE_URL",
            "TITLE_USER",
            "TITLE_PASS",
            "JC_API",
            "JC_ORG",
            "FW_SERVER_HOST",
            "FW_SERVER_PORT",
            "FW_ADMIN_USER",
            "FW_ADMIN_PASSWORD",
            "BES_ROOT_SERVER",
            "BES_USERNAME",
            "BES_PASSWORD",
            "CLIENT_ID",
            "CLIENT_SECRET",
            "TENANT_ID",
            "VIRUSTOTAL_API_KEY",
        ],
    ) -> str | None: ...

    @overload
    def __getitem__(
        self,
        key: Literal[
            "FAIL_RECIPES_WITHOUT_TRUST_INFO", "STOP_IF_NO_JSS_UPLOAD", "CLOUD_DP"
        ],
    ) -> bool | None: ...

    @overload
    def __getitem__(
        self, key: Literal["SMB_SHARES"]
    ) -> list[dict[str, str]] | None: ...

    # All other keys
    @overload
    def __getitem__(self, key: str) -> Any: ...

    def __getitem__(self, key: str) -> Any:
        """Retrieves a preference value by key.

        This method first checks if the key exists in the known preferences.

        Args:
            key: The name of the preference to retrieve.

        Returns:
            The value of the preference.

        Raises:
            KeyError: If the key is not found in the preferences.
        """
        if key in self._prefs:
            return self._prefs[key]
        raise KeyError(f"No key matching '{key}' in {__name__}")  # noqa: TRY003

    def __setitem__(self, key: str, value: Any) -> None:
        """Sets a preference value by key.

        Args:
            key: The name of the preference to set.
            value: The value to set for the preference.
        """
        self._prefs[key] = value

    @overload
    def get(
        self,
        key: Literal["CACHE_DIR", "RECIPE_REPO_DIR"],
        default: object = None,
    ) -> Path: ...

    @overload
    def get(
        self,
        key: Literal["MUNKI_REPO"],
        default: object = None,
    ) -> Path | None: ...

    @overload
    def get(
        self,
        key: Literal["RECIPE_SEARCH_DIRS", "RECIPE_OVERRIDE_DIRS"],
        default: object = None,
    ) -> list[Path]: ...

    @overload
    def get(
        self,
        key: Literal[
            "GITHUB_TOKEN",
            "SMB_URL",
            "SMB_USERNAME",
            "SMB_PASSWORD",
            "PATCH_URL",
            "PATCH_TOKEN",
            "TITLE_URL",
            "TITLE_USER",
            "TITLE_PASS",
            "JC_API",
            "JC_ORG",
            "FW_SERVER_HOST",
            "FW_SERVER_PORT",
            "FW_ADMIN_USER",
            "FW_ADMIN_PASSWORD",
            "BES_ROOT_SERVER",
            "BES_USERNAME",
            "BES_PASSWORD",
            "CLIENT_ID",
            "CLIENT_SECRET",
            "TENANT_ID",
            "VIRUSTOTAL_API_KEY",
        ],
        default: object = None,
    ) -> str | None: ...

    @overload
    def get(
        self,
        key: Literal[
            "FAIL_RECIPES_WITHOUT_TRUST_INFO", "STOP_IF_NO_JSS_UPLOAD", "CLOUD_DP"
        ],
        default: object = None,
    ) -> bool | None: ...

    @overload
    def get(self, key: Literal["SMB_SHARES"]) -> list[dict[str, str]] | None: ...

    # All other keys
    @overload
    def get(self, key: str, default: T = None) -> Any | T: ...

    def get(self, key: str, default: T = None) -> Any | T:
        """Retrieves a preference value by key with a default.

        This method first checks if the key exists in the known preferences.
        If the key is not found, it returns the specified default value.

        Args:
            key: The name of the preference to retrieve.
            default: The value to return if the key is not found.

        Returns:
            The value of the preference, or the default value if the key is not found.
        """
        try:
            return self.__getitem__(key)
        except KeyError:
            return default
