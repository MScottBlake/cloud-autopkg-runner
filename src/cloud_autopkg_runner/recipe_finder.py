"""Provides utilities for locating AutoPkg recipes within specified directories."""

import asyncio
from pathlib import Path

from cloud_autopkg_runner import AutoPkgPrefs, logging_config
from cloud_autopkg_runner.exceptions import RecipeLookupException


class RecipeFinder:
    """Locates AutoPkg recipes within configured search paths.

    This class encapsulates the logic for finding AutoPkg recipe files based
    on a given recipe name and a set of pre-defined search directories. It supports
    both direct file lookup and recursive searching within those directories,
    with an optional limit on recursion depth to optimize performance and prevent
    excessive searching.
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
        autopkg_prefs: AutoPkgPrefs | None = None,
        max_recursion_depth: int = 3,
    ) -> None:
        """Initializes a RecipeFinder instance.

        Args:
            autopkg_prefs: An optional AutoPkgPrefs instance containing the
                configured recipe override and search directories. If None,
                a default AutoPkgPrefs instance will be created.
            max_recursion_depth: The maximum number of directory levels to
                descend when performing a recursive search for a recipe.
                Defaults to 3.
        """
        self.logger = logging_config.get_logger(__name__)
        self.max_recursion_depth: int = max_recursion_depth

        if not autopkg_prefs:
            autopkg_prefs = AutoPkgPrefs()

        self.lookup_dirs: list[Path] = (
            autopkg_prefs.recipe_override_dirs + autopkg_prefs.recipe_search_dirs
        )

    async def find_recipe(self, recipe_name: str) -> Path:
        """Locates the path to an AutoPkg recipe.

        This method searches for an AutoPkg recipe with the given name across all
        configured `lookup_dirs`. It first attempts a direct lookup in each
        directory and then, if not found, performs a recursive search within
        that directory up to `max_recursion_depth`. The search order prioritizes
        override directories and direct matches for efficiency.

        Args:
            recipe_name: The name of the AutoPkg recipe to find. This can be
                a simple name (e.g., "GoogleChrome.pkg") or include a valid
                AutoPkg recipe extension (e.g., "GoogleChrome.pkg.recipe").

        Returns:
            The `Path` object corresponding to the located AutoPkg recipe file.

        Raises:
            RecipeLookupException: If no matching recipe file is found after
                searching all configured directories and their recursive paths.
        """
        possible_filenames: list[str] = self.possible_file_names(recipe_name)

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
        """Generates a list of possible AutoPkg recipe file names.

        This utility function takes a base recipe name and constructs a list
        of potential filenames by appending all `VALID_EXTENSIONS`. If the
        provided `recipe_name` already ends with one of the valid extensions,
        it is assumed to be a complete filename and returned as the sole
        element in the list.

        Args:
            recipe_name: The base name of the AutoPkg recipe (e.g., "GoogleChrome.pkg")
                or a full recipe filename (e.g., "GoogleChrome.pkg.recipe").

        Returns:
            A `list` of strings, where each string is a possible filename
            for the AutoPkg recipe.
        """
        if recipe_name.endswith(self.VALID_EXTENSIONS):
            return [recipe_name]
        return [recipe_name + ext for ext in self.VALID_EXTENSIONS]

    def _find_in_directory(self, directory: Path, filenames: list[str]) -> Path | None:
        """Attempts to find a matching recipe file directly within a given directory.

        This private helper method performs a non-recursive search. It checks
        if any of the provided `filenames` exist directly within the `directory`.

        Args:
            directory: The `Path` object representing the directory to search in.
                This path will be expanded using `expanduser()`.
            filenames: A `list` of strings, where each string is a possible
                filename for the recipe.

        Returns:
            The `Path` object to the recipe file if a direct match is found,
            otherwise `None`.
        """
        expanded_directory: Path = directory.expanduser()
        for filename in filenames:
            direct_path: Path = expanded_directory / filename
            if direct_path.exists():
                self.logger.info("Found recipe at: %s", direct_path)
                return direct_path
        return None

    async def _find_in_directory_recursively(
        self, directory: Path, filenames: list[str]
    ) -> Path | None:
        """Searches recursively for a recipe within the given directory.

        This private helper method initiates a recursive search for any of the
        provided `filenames` starting from the `directory`. The recursion depth
        is limited by `self.max_recursion_depth`.

        Args:
            directory: The `Path` object representing the directory to start
                the recursive search from. This path will be expanded using
                `expanduser()`.
            filenames: A `list` of strings, where each string is a possible
                filename to search for.

        Returns:
            The `Path` object to the recipe file if found recursively, otherwise `None`.
        """
        expanded_directory: Path = directory.expanduser()
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

        This private helper method leverages `Path.rglob()` to efficiently
        search for a `target_filename` within the `root` directory and its
        subdirectories. It limits the search depth to `max_depth` to prevent
        excessive recursion and improve performance. The file system traversal
        is offloaded to a separate thread using `asyncio.to_thread` to avoid
        blocking the event loop.

        Args:
            root: The `Path` object representing the directory to start the
                recursive search from.
            target_filename: The exact name of the file to search for (e.g.,
                "GoogleChrome.recipe").
            max_depth: The maximum number of directory levels to descend during
                the recursive search.

        Returns:
            The `Path` object to the found file, or `None` if the file is not
            found within the specified depth or an `OSError` occurs.
        """
        try:
            # Use asyncio.to_thread since this is a potentially long-running operation
            paths: list[Path] = await asyncio.to_thread(
                list, root.rglob(target_filename)
            )

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
        """Searches for a recipe within a single directory, prioritizing direct match.

        This private helper method orchestrates the search within a given
        `directory`. It first attempts to find the recipe files specified by
        `filenames` directly within the `directory`. If no direct match is
        found, it then proceeds with a recursive search within the same `directory`.
        This two-stage approach optimizes for common cases where recipes are
        expected at the top level of search paths.

        Args:
            directory: The `Path` object representing the directory to search within.
            filenames: A `list` of strings, where each string is a possible
                filename to search for.

        Returns:
            The `Path` object to the recipe file if found (either directly or
            recursively), otherwise `None`.
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
        """Checks if a candidate path is within the maximum depth from a base path.

        This static private helper method calculates the relative depth of
        `candidate` path with respect to the `base` path. It helps in enforcing
        the `max_recursion_depth` constraint during recursive file searches.

        Args:
            base: The `Path` object representing the base directory path.
            candidate: The `Path` object to the candidate file or directory
                whose depth is to be checked.
            max_depth: The maximum allowed depth (number of directory levels)
                from the `base` path. A `max_depth` of 0 means only the `base`
                directory itself.

        Returns:
            `True` if the `candidate` path is within or equal to the allowed
            `max_depth` from the `base` path, `False` otherwise or if `candidate`
            is not a child of `base`.
        """
        try:
            relative: Path = candidate.relative_to(base)
            return len(relative.parts) <= max_depth
        except ValueError:
            return False
