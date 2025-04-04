"""Module for handling AutoPkg recipe processing in cloud-autopkg-runner.

This module defines classes and functions for representing, parsing,
and processing AutoPkg recipes. It provides tools for extracting
information from recipes, generating lists of recipes, and performing
other recipe-related operations.

Key classes:
- `Recipe`: Represents an AutoPkg recipe and provides methods for accessing
  recipe metadata, parsing the recipe contents, running the recipe, and
  managing trust information.
"""

import plistlib
import tempfile
from collections.abc import Iterable
from datetime import datetime, timezone
from enum import Enum, StrEnum, auto
from pathlib import Path
from typing import Any, TypedDict

import yaml

from cloud_autopkg_runner import AppConfig, logger
from cloud_autopkg_runner.autopkg_prefs import AutoPkgPrefs
from cloud_autopkg_runner.exceptions import (
    InvalidPlistContents,
    InvalidYamlContents,
    RecipeFormatException,
    RecipeInputException,
    RecipeLookupException,
)
from cloud_autopkg_runner.metadata_cache import (
    DownloadMetadata,
    RecipeCache,
    get_file_metadata,
    save_metadata_cache,
)
from cloud_autopkg_runner.recipe_report import ConsolidatedReport, RecipeReport
from cloud_autopkg_runner.shell import run_cmd


class RecipeContents(TypedDict):
    """Represents the structure of a recipe's contents.

    This dictionary represents the parsed contents of an AutoPkg recipe file,
    including its description, identifier, input variables, minimum version,
    parent recipe, and process steps.

    Attributes:
        Description: A brief description of the recipe.
        Identifier: A unique identifier for the recipe.
        Input: A dictionary of input variables used by the recipe.
        MinimumVersion: The minimum AutoPkg version required to run the recipe.
        ParentRecipe: The identifier of the recipe's parent recipe (if any).
        Process: A list of dictionaries, where each dictionary defines a step
            in the recipe's processing workflow.
    """

    Description: str | None
    Identifier: str
    Input: dict[str, Any]
    MinimumVersion: str | None
    ParentRecipe: str | None
    Process: Iterable[dict[str, Any]]


class RecipeFormat(StrEnum):
    """Enumerates the supported recipe file formats.

    This enum defines the possible file formats for AutoPkg recipes,
    including YAML and PLIST.

    Values:
        YAML: Represents a recipe in YAML format.
        PLIST: Represents a recipe in plist format (either XML or binary).
    """

    YAML = "yaml"
    PLIST = "plist"


class Recipe:
    """Represents an AutoPkg recipe.

    This class provides methods for accessing recipe metadata, parsing the recipe
    contents, running the recipe, and managing trust information.

    Attributes:
        _path: Path to the recipe file.
        _format: RecipeFormat enum value representing the file format.
        _contents: RecipeContents dictionary containing the parsed recipe contents.
        _trusted: TrustInfoVerificationState enum value representing the trust
            information verification state.
        _result: RecipeReport object for storing the results of running the recipe.
    """

    def __init__(self, recipe_name: str, report_dir: Path | None = None) -> None:
        """Initialize a Recipe object.

        Args:
            recipe_name: Path to the recipe file.
            report_dir: Path to the report directory. If None, a temporary
                directory is created.
        """
        self._name: str = recipe_name

        try:
            self._path: Path = self._find_recipe(recipe_name)
        except RecipeLookupException as exc:
            logger.error(exc)
            raise

        self._format: RecipeFormat = self.format()
        self._contents: RecipeContents = self._get_contents()
        self._trusted: TrustInfoVerificationState = TrustInfoVerificationState.UNTESTED

        if report_dir is None:
            report_dir = Path(tempfile.mkdtemp(prefix="autopkg_"))

        report_path: Path = report_dir / Path(self.name).stem
        counter = 1
        original_report_path = report_path
        while report_path.exists():
            report_path = original_report_path.with_name(
                f"{original_report_path.name}_{counter}"
            )
            counter += 1

        self._result: RecipeReport = RecipeReport(report_path)

    @property
    def contents(self) -> RecipeContents:
        """Returns the recipe's contents as a dictionary.

        Returns:
            The recipe's contents as a RecipeContents TypedDict.
        """
        return self._contents

    @property
    def description(self) -> str:
        """Returns the recipe's description.

        Returns:
            The recipe's description as a string.  Returns an empty string
            if the recipe does not have a description.
        """
        if self._contents["Description"] is None:
            return ""
        return self._contents["Description"]

    @property
    def identifier(self) -> str:
        """Returns the recipe's identifier.

        Returns:
            The recipe's identifier as a string.
        """
        return self._contents["Identifier"]

    @property
    def input(self) -> dict[str, Any]:
        """Returns the recipe's input dictionary.

        Returns:
            The recipe's input dictionary, containing the input variables
            used by the recipe.
        """
        return self._contents["Input"]

    @property
    def input_name(self) -> str:
        """Returns the recipe's NAME input variable.

        Returns:
            The recipe's NAME input variable as a string.

        Raises:
            RecipeInputException: If the recipe does not contain a NAME input variable.
        """
        try:
            return self._contents["Input"]["NAME"]
        except AttributeError as exc:
            raise RecipeInputException(self._path) from exc

    @property
    def minimum_version(self) -> str:
        """Returns the recipe's minimum version.

        Returns:
            The recipe's minimum version as a string.  Returns an empty string
            if the recipe does not have a minimum version specified.
        """
        if self._contents["MinimumVersion"] is None:
            return ""
        return self._contents["MinimumVersion"]

    @property
    def name(self) -> str:
        """Returns the recipe's filename.

        Returns:
            The recipe's filename (without the extension) as a string.
        """
        return self._path.name

    @property
    def parent_recipe(self) -> str:
        """Returns the recipe's parent recipe identifier.

        Returns:
            The recipe's parent recipe identifier as a string.  Returns an empty
            string if the recipe does not have a parent recipe.
        """
        if self._contents["ParentRecipe"] is None:
            return ""
        return self._contents["ParentRecipe"]

    @property
    def process(self) -> Iterable[dict[str, Any]]:
        """Returns the recipe's process array.

        Returns:
            The recipe's process array, which is an iterable of dictionaries
            defining the steps in the recipe's processing workflow.
        """
        return self._contents["Process"]

    def _autopkg_run_cmd(self, *, check: bool = False) -> list[str]:
        """Constructs the command-line arguments for running AutoPkg.

        Args:
            check: A boolean value to add `--check` to the `autopkg run` command.

        Returns:
            The command to run AutoPkg with this recipe.
        """
        cmd = [
            "/usr/local/bin/autopkg",
            "run",
            self.name,
            f"--report-plist={self._result.file_path()}",
        ]

        if AppConfig.verbosity_int(-1) > 0:
            cmd.append(AppConfig.verbosity_str(-1))

        if check:
            cmd.append("--check")

        return cmd

    def _extract_download_paths(
        self, download_items: list[dict[str, Any]]
    ) -> list[str]:
        """Extracts 'download_path' values from a list of dictionaries.

        This function assumes that each dictionary in the input list has a structure
        like: {'downloaded_items': [{'download_path': 'path_to_file'}]}

        Args:
            download_items: A list of dictionaries, where each dictionary is
                expected to have a "downloaded_items" key containing a list of
                dictionaries, and each of those dictionaries is expected to have
                a "download_path" key with a string value.

        Returns:
            A list of strings, where each string is the 'download_path' value from
            the first dictionary in the "downloaded_items" list of each input
            dictionary. Returns an empty list if the input is empty, any of the
            intermediate keys are missing, or the "downloaded_items" list is empty.
        """
        if not download_items:
            return []

        return [item["download_path"] for item in download_items]

    def _find_recipe(self, recipe_name: str) -> Path:
        """Locates the recipe path.

        Returns:
            Path of a given recipe
        """
        autopkg_preferences = AutoPkgPrefs()
        lookup_dirs: list[Path] = list(
            autopkg_preferences["RECIPE_OVERRIDE_DIRS"]
        ) + list(autopkg_preferences["RECIPE_SEARCH_DIRS"])

        if recipe_name.endswith((".recipe", ".recipe.plist", ".recipe.yaml")):
            possible_filenames = [recipe_name]
        else:
            possible_filenames = [
                recipe_name + ".recipe",
                recipe_name + ".recipe.plist",
                recipe_name + ".recipe.yaml",
            ]

        for lookup_path in lookup_dirs:
            path = lookup_path.expanduser()
            for filename in possible_filenames:
                recipe_path = path / filename
                if recipe_path.exists():
                    return recipe_path

        raise RecipeLookupException(recipe_name)

    def _get_contents(self) -> RecipeContents:
        """Read and parse the recipe file.

        Returns:
            A dictionary containing the recipe's contents.

        Raises:
            InvalidFileContents: If the file is invalid or cannot be parsed.
        """
        file_contents = self._path.read_text()

        if self._format == RecipeFormat.YAML:
            return self._get_contents_yaml(file_contents)
        return self._get_contents_plist(file_contents)

    def _get_contents_plist(self, file_contents: str) -> RecipeContents:
        """Parse a recipe in PLIST format.

        Args:
            file_contents: The recipe file contents as a string.

        Returns:
            A dictionary containing the recipe's contents.

        Raises:
            InvalidPlistContents: If the plist file is invalid.
        """
        try:
            return plistlib.loads(file_contents.encode())
        except plistlib.InvalidFileException as exc:
            raise InvalidPlistContents(self._path) from exc

    def _get_contents_yaml(self, file_contents: str) -> RecipeContents:
        """Parse a recipe in YAML format.

        Args:
            file_contents: The recipe file contents as a string.

        Returns:
            A dictionary containing the recipe's contents.

        Raises:
            InvalidYamlContents: If the yaml file is invalid.
        """
        try:
            return yaml.safe_load(file_contents)
        except yaml.YAMLError as exc:
            raise InvalidYamlContents(self._path) from exc

    def _get_metadata(self, download_items: list[dict[str, str]]) -> RecipeCache:
        """Extracts metadata from downloaded files and returns a RecipeCache object.

        Args:
            download_items: A list of dictionaries representing downloaded items,
                typically obtained from the AutoPkg report.

        Returns:
            A RecipeCache object containing metadata about the downloaded files.
        """
        metadata_list: list[DownloadMetadata] = []

        for downloaded_item in self._extract_download_paths(download_items):
            downloaded_item_path = Path(downloaded_item)
            metadata_list.append(
                {
                    "etag": get_file_metadata(
                        downloaded_item_path, "com.github.autopkg.etag"
                    ),
                    "file_size": downloaded_item_path.stat().st_size,
                    "last_modified": get_file_metadata(
                        downloaded_item_path, "com.github.autopkg.last-modified"
                    ),
                    "file_path": downloaded_item,
                }
            )

        return {
            "timestamp": str(datetime.now(tz=timezone.utc)),
            "metadata": metadata_list,
        }

    def compile_report(self) -> ConsolidatedReport:
        """Compiles a consolidated report from the recipe report file.

        Returns:
            A ConsolidatedReport object containing information about failed items,
            downloaded items, package builds, and Munki imports.
        """
        self._result.refresh_contents()
        return self._result.consolidate_report()

    def format(self) -> RecipeFormat:
        """Determine the recipe's format based on its file extension.

        Returns:
            A RecipeFormat enum value.

        Raises:
            RecipeFormatException: If the file extension is not recognized.
        """
        if self._path.suffix == ".yaml":
            return RecipeFormat.YAML
        if self._path.suffix in [".plist", ".recipe"]:
            return RecipeFormat.PLIST
        raise RecipeFormatException(self._path.suffix)

    async def run(self) -> ConsolidatedReport:
        """Runs the recipe and saves metadata.

        This method first performs a check phase to determine if there are any
        updates available. If updates are available, it extracts metadata from
        the downloaded files, saves the metadata to the cache, and then performs
        a full run of the recipe.

        Returns:
            A ConsolidatedReport object containing the results of the recipe run.
        """
        output = await self.run_check_phase()
        if output["downloaded_items"]:
            metadata = self._get_metadata(output["downloaded_items"])
            save_metadata_cache(AppConfig.cache_file(), self.name, metadata)

            return await self.run_full()
        return output

    async def run_check_phase(self) -> ConsolidatedReport:
        """Performs the check phase of the recipe.

        This involves invoking AutoPkg with the `--check` flag to determine
        if there are any updates available for the software managed by the
        recipe.

        Returns:
            A ConsolidatedReport object containing the results of the check phase.
        """
        logger.debug(f"Performing Check Phase on {self.name}...")

        returncode, _stdout, stderr = await run_cmd(
            self._autopkg_run_cmd(check=True), check=False
        )

        if returncode != 0:
            if not stderr:
                stderr = "<Unknown Error>"
            logger.error(
                f"An error occurred while running the check phase, "
                f"on {self.name}: {stderr}"
            )

        return self.compile_report()

    async def run_full(
        self,
    ) -> ConsolidatedReport:
        """Performs an `autopkg run` of the recipe.

        This method executes the full AutoPkg recipe, including downloading
        files, building packages, and importing items into Munki, depending
        on the recipe's process steps.

        Returns:
            A ConsolidatedReport object containing the results of the full recipe run.
        """
        logger.debug(f"Performing AutoPkg Run on {self.name}...")

        returncode, _stdout, stderr = await run_cmd(
            self._autopkg_run_cmd(check=False), check=False
        )

        if returncode != 0:
            if not stderr:
                stderr = "<Unknown Error>"
            logger.error(f"An error occurred while running {self.name}: {stderr}")

        return self.compile_report()

    async def update_trust_info(self) -> bool:
        """Update trust info for the recipe.

        This involves calling the autopkg `update-trust-info` command.

        Returns:
            True if the trust info was successfully updated, False otherwise.
        """
        logger.debug(f"Updating trust info for {self.name}...")

        cmd = [
            "/usr/local/bin/autopkg",
            "update-trust-info",
            self.name,
            f"--override-dir={self._path.parent}",
        ]

        returncode, stdout, _stderr = await run_cmd(cmd)

        logger.info(stdout)
        self._trusted = TrustInfoVerificationState.UNTESTED

        if returncode == 0:
            logger.info(f"Trust info update for {self.name} successful.")
            return True

        logger.warning(f"Trust info update for {self.name} failed.")
        return False

    async def verify_trust_info(self) -> bool:
        """Verify the trust info.

        Calls autopkg with the `verify-trust-info` command.

        Returns:
            True if the trust info is trusted, False if it is untrusted, or UNTESTED if
                it hasn't been tested yet.
        """
        if self._trusted == TrustInfoVerificationState.UNTESTED:
            logger.debug(f"Verifying trust info for {self.name}...")

            cmd = [
                "/usr/local/bin/autopkg",
                "verify-trust-info",
                self.name,
                f"--override-dir={self._path.parent}",
            ]

            if AppConfig.verbosity_int() > 0:
                cmd.append(AppConfig.verbosity_str())

            returncode, _stdout, _stderr = await run_cmd(cmd, check=False)

            if returncode == 0:
                logger.info(f"Trust info verification for {self.name} successful.")
                self._trusted = TrustInfoVerificationState.TRUSTED
            else:
                logger.warning(f"Trust info verification for {self.name} failed.")
                self._trusted = TrustInfoVerificationState.FAILED

        return self._trusted.value


class TrustInfoVerificationState(Enum):
    """Enum for whether trust info is tested, successful, or failed.

    This enum represents the possible states of trust information verification
    for an AutoPkg recipe.

    Values:
        UNTESTED: Trust information has not been verified.
        FAILED: Trust information verification failed.
        TRUSTED: Trust information verification was successful.
    """

    UNTESTED = auto()
    FAILED = False
    TRUSTED = True
