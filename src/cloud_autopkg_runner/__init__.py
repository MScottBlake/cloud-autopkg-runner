"""The cloud-autopkg-runner package.

This package provides asynchronous tools and utilities for managing
AutoPkg recipes and workflows. It includes modules for handling
metadata caching, recipe processing, shell command execution, and
more.

Key features include:
- Asynchronous execution of AutoPkg recipes for improved performance.
- Robust error handling and logging.
- Integration with AutoPkg's preference system.
- Flexible command-line interface for specifying recipes and options.
- Metadata caching to reduce redundant downloads.
"""

import logging
import sys
from pathlib import Path

# Create a logger instance
logger: logging.Logger = logging.getLogger(__name__)


class AppConfig:
    """Manages application-wide configuration settings.

    This class uses class variables to store configuration data and
    class methods to manage and access that data. It handles
    the initialization of the logging system and provides access
    to configuration parameters such as verbosity level, log file path,
    and the metadata cache file path.
    """

    _cache_file: Path = Path("metadata_cache.json")
    _log_file: Path | None = None
    _max_concurrency: int = 10
    _report_dir: Path = Path("recipe_reports")
    _verbosity_level: int = 0

    @classmethod
    def set_config(
        cls,
        *,
        max_concurrency: int | None = None,
        verbosity_level: int | None = None,
        cache_file: Path | None = None,
        report_dir: Path | None = None,
        log_file: Path | None = None,
    ) -> None:
        """Set the application configuration parameters.

        This method updates the class variables that store the verbosity
        level, log file path, and cache file path. It does *not* initialize
        the logging system; `initialize_logger()` must be called separately.

        Args:
            verbosity_level: The integer verbosity level (0, 1, 2, etc.).
            max_concurrency: The integer concurrency limit.
            log_file: Optional path to the log file. If specified, logging
                output will be written to this file in addition to the console.
            cache_file: The path to the cache file.
            report_dir: The path to the directory used for storing AutoPkg recipe
                recipts and recipe reports.
        """
        if verbosity_level is not None:
            cls._verbosity_level = verbosity_level

        if log_file is not None:
            cls._log_file = log_file

        if cache_file is not None:
            cls._cache_file = cache_file

        if max_concurrency is not None:
            cls._max_concurrency = max_concurrency

        if report_dir is not None:
            cls._report_dir = report_dir

    @classmethod
    def initialize_logger(cls) -> None:
        """Initialize the logging system.

        Configures the root logger with a console handler and an optional
        file handler. The console handler's log level is determined by the
        current verbosity level, while the file handler (if enabled) logs at
        the DEBUG level. The logging is initialized using values in the class.

        The logging formatters include the module name, log level, and message,
        with the file handler also including a timestamp.
        """
        log_levels = [logging.WARNING, logging.INFO, logging.DEBUG]
        level = log_levels[min(cls._verbosity_level, len(log_levels) - 1)]

        logger.setLevel(logging.DEBUG)

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_formatter = logging.Formatter(
            "%(module)-20s %(levelname)-8s %(message)s"
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

        # File handler (optional)
        if cls._log_file:
            file_handler = logging.FileHandler(cls._log_file, mode="w")
            file_handler.setLevel(logging.DEBUG)
            file_formatter = logging.Formatter(
                "%(asctime)s %(module)-20s %(levelname)-8s %(message)s",
                datefmt="%m-%d %H:%M",
            )
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)

    @classmethod
    def cache_file(cls) -> Path:
        """Returns the path to the metadata cache file."""
        return cls._cache_file

    @classmethod
    def log_file(cls) -> Path | None:
        """Returns the path to the log file, if any.

        Returns:
            The path to the log file as a `pathlib.Path`, or None if no log file is
            configured.
        """
        return cls._log_file

    @classmethod
    def report_dir(cls) -> Path:
        """Returns the directory path for recipe reports.

        Returns:
            The path to the report directory as a `pathlib.Path`.
        """
        return cls._report_dir

    @classmethod
    def max_concurrency(cls) -> int:
        """Returns the maximum number of concurrent tasks.

        Returns:
            Returns the maximum number of concurrent tasks as an integer.
        """
        return cls._max_concurrency

    @classmethod
    def verbosity_int(cls, delta: int = 0) -> int:
        """Returns the verbosity level.

        Args:
            delta: An optional integer to add to the base verbosity level.
                This can be used to temporarily increase or decrease the
                verbosity for specific operations.

        Returns:
            The integer verbosity level, adjusted by the delta.
        """
        level = cls._verbosity_level + delta
        if level <= 0:
            return 0
        return level

    @classmethod
    def verbosity_str(cls, delta: int = 0) -> str:
        """Convert an integer verbosity level to a string of `-v` flags.

        Args:
            delta: An optional integer to add to the base verbosity level.
                This can be used to temporarily increase or decrease the
                verbosity for specific operations.

        Returns:
            A string consisting of `-` followed by `v` repeated `verbosity_level`
            times. Returns an empty string if verbosity_level is 0 or negative.

        Examples:
            verbosity_str(0) == ""
            verbosity_str(1) == "-v"
            verbosity_str(2) == "-vv"
            verbosity_str(3) == "-vvv"
        """
        level = cls._verbosity_level + delta
        if level <= 0:
            return ""
        return "-" + "v" * level


# Located here to prevent circular imports
def list_possible_file_names(recipe_name: str) -> list[str]:
    """Generate a list of possible AutoPkg recipe file names.

    Given a recipe name, this function returns a list of possible file names
    by appending common AutoPkg recipe file extensions. If the recipe name
    already ends with a known extension, it returns a list containing only the
    original recipe name.

    Args:
        recipe_name: The name of the AutoPkg recipe.

    Returns:
        A list of possible file names for the recipe.
    """
    if recipe_name.endswith((".recipe", ".recipe.plist", ".recipe.yaml")):
        return [recipe_name]

    return [
        recipe_name + ".recipe",
        recipe_name + ".recipe.plist",
        recipe_name + ".recipe.yaml",
    ]
