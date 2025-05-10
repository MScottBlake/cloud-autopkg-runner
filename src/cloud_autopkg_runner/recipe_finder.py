"""Provides utilities for locating AutoPkg recipes within specified directories."""

import asyncio
from pathlib import Path

from cloud_autopkg_runner import AutoPkgPrefs, logging_config
from cloud_autopkg_runner.exceptions import RecipeLookupException


class RecipeFinder:
    """Locates AutoPkg recipes within configured search paths.

    This class encapsulates the logic for finding AutoPkg recipe files based
    on a given recipe name and a set of pre-defined search directories,
    including support for recursive searching and limiting recursion depth.
    """

    # https://github.com/autopkg/autopkg/wiki/Recipe-Format#recipe-file-extensions
    VALID_EXTENSIONS: tuple[str, ...] = (
        ".recipe",
        ".recipe.plist",
        ".recipe.yaml",
    )
    """A tuple of valid file extensions for AutoPkg recipes."""

    def __init__(
        self,
        autopkg_preferences: AutoPkgPrefs | None = None,
        max_recursion_depth: int = 3,
    ) -> None:
        """Initializes a RecipeFinder instance."""
        self.logger = logging_config.get_logger(__name__)
        self.autopkg_preferences = autopkg_preferences or AutoPkgPrefs()
        self.max_recursion_depth = max_recursion_depth

        self.lookup_dirs: list[Path] = (
            self.autopkg_preferences.recipe_override_dirs
            + self.autopkg_preferences.recipe_search_dirs
        )

    async def find_recipe(self, recipe_name: str) -> Path:
        """Locates the recipe path.

        Finds the path to the AutoPkg recipe with the given name, searching through the
        recipe override directory, search directory and recursively if required.

        Args:
            recipe_name: The name of the AutoPkg recipe.

        Returns:
            The Path to a given recipe if successful

        Raises:
            RecipeLookupException: If no matching file is found after searching all
                directories and recursive paths.
        """
        possible_filenames = self.possible_file_names(recipe_name)

        for lookup_path in self.lookup_dirs:
            if recipe_path := await self._search_directory(
                lookup_path, possible_filenames
            ):
                return recipe_path

        self.logger.error(
            "Recipe '%s' not found in any lookup directories.", recipe_name
        )
        raise RecipeLookupException(recipe_name)

    def possible_file_names(self, recipe_name: str) -> list[str]:
        """Generate a list of possible AutoPkg recipe file names.

        Given a recipe name, this function returns a list of possible file names
        by appending valid AutoPkg recipe file extensions. If the recipe name
        already ends with a valid extension, it returns a list containing only the
        original recipe name.

        Args:
            recipe_name: The name of the AutoPkg recipe.

        Returns:
            A list of possible file names for the recipe.
        """
        if recipe_name.endswith(self.VALID_EXTENSIONS):
            return [recipe_name]
        return [recipe_name + ext for ext in self.VALID_EXTENSIONS]

    def _find_in_directory(self, directory: Path, filenames: list[str]) -> Path | None:
        """Attempts to find a match for a recipe in the given directory.

        This function does not search subdirectories.

        Args:
            directory: The directory to search in.
            filenames: A list of possible filenames.

        Returns:
            The Path to the recipe if a direct match is found, otherwise None.
        """
        expanded_directory = directory.expanduser()
        for filename in filenames:
            direct_path = expanded_directory / filename
            if direct_path.exists():
                self.logger.info("Found recipe at: %s", direct_path)
                return direct_path
        return None

    async def _find_in_directory_recursively(
        self, directory: Path, filenames: list[str]
    ) -> Path | None:
        """Searches recursively for a recipe within the given directory.

        Args:
            directory: The directory to start the recursive search from.
            filenames: A list of possible filenames to search for.

        Returns:
            The Path to the recipe if found recursively, otherwise None.
        """
        expanded_directory = directory.expanduser()
        for filename in filenames:
            if match := await self._find_recursively(
                expanded_directory, filename, self.max_recursion_depth
            ):
                self.logger.info("Found recipe via recursive search at: %s", match)
                return match
        return None

    async def _find_recursively(
        self, root: Path, target_filename: str, max_depth: int
    ) -> Path | None:
        """Recursively searches for a file with a specific name within a directory.

        Limits the search depth to prevent excessive recursion. This method helps
        locate recipe files that may be located in subdirectories within the
        configured search paths.

        Args:
            root: The directory to start the recursive search from.
            target_filename: The name of the file to search for.
            max_depth: The maximum recursion depth.

        Returns:
            The Path to the found file, or None if the file is not found within
            the specified depth.
        """
        try:
            # Use asyncio.to_thread since this is a potentially long-running operation
            paths = await asyncio.to_thread(list, root.rglob(target_filename))

            for path in paths:
                if not path.is_file():
                    continue

                if not self._path_within_depth(root, path, max_depth):
                    self.logger.debug("Skipping %s (depth > %s)", path, max_depth)
                    continue

                self.logger.debug("Found candidate: %s", path)
                return path

        except OSError as e:
            self.logger.warning("OSError during recursive search in %s: %s", root, e)
        return None

    async def _search_directory(
        self, directory: Path, filenames: list[str]
    ) -> Path | None:
        """Searches for a recipe within a single directory.

        First, it attempts to find the recipe in the top-level of the directory. If
        that fails, it attempts a recursive search of the directory. The two stage
        search is performed to increase performance when specifying the specific
        directory to search.

        Args:
            directory: The directory to search within.
            filenames: A list of possible filenames to search for.

        Returns:
            The Path to the recipe if found, otherwise None.
        """
        if recipe_path := self._find_in_directory(directory, filenames):
            return recipe_path

        if recipe_path := await self._find_in_directory_recursively(
            directory, filenames
        ):
            return recipe_path

        return None

    @staticmethod
    def _path_within_depth(base: Path, candidate: Path, max_depth: int) -> bool:
        """Checks if a path is within the maximum allowed depth from the base path.

        Args:
            base: The base directory path.
            candidate: The path to the candidate file or directory.
            max_depth: The maximum allowed depth (number of directory levels).

        Returns:
            True if the candidate path is within the allowed depth, False otherwise.
        """
        try:
            relative = candidate.relative_to(base)
            return len(relative.parts) <= max_depth
        except ValueError:
            return False
