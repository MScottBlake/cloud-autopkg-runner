"""Application settings module (Singleton Pattern with Properties).

This module defines the `Settings` class, which implements a Singleton pattern
to ensure only one instance of application settings is created. It provides
a type-safe and centralized way to manage application-wide configuration
parameters such as file paths, verbosity level, and concurrency limits.

The `Settings` class uses properties and custom setters to control access
to and modification of the settings, including validation where appropriate.

Classes:
    Settings: Manages application settings using properties and custom setters.

Exceptions:
    SettingsValidationError: Raised when a setting fails validation.
"""

from pathlib import Path
from typing import Any

from cloud_autopkg_runner.exceptions import SettingsValidationError


class SettingsImpl:
    """Manages application settings using properties and custom setters.

    Ensures only one instance is available globally. Provides type-safe
    access and validation for setting application configurations.

    Attributes:
        _instance: The singleton instance of the Settings class.
    """

    _instance: "SettingsImpl | None" = None

    def __new__(cls, *args: Any, **kwargs: Any) -> "SettingsImpl":  # noqa: ANN401
        """Create a new instance of Settings if one doesn't exist.

        This `__new__` method implements the Singleton pattern, ensuring
        that only one instance of the `Settings` class is ever created.
        If an instance already exists, it is returned; otherwise, a new
        instance is created and stored for future use.

        Args:
            *args: Arbitrary positional arguments.
            **kwargs: Arbitrary keyword arguments.

        Returns:
            The Settings instance.
        """
        if not cls._instance:
            cls._instance = super().__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(
        self,
        *,
        cache_file: Path = Path("metadata_cache.json"),
        log_file: Path | None = None,
        max_concurrency: int = 10,
        report_dir: Path = Path("recipe_reports"),
        verbosity_level: int = 0,
    ) -> None:
        """Initialize the application settings.

        Sets the default values for the application settings. This method
        is called only once due to the Singleton pattern implemented in
        `__new__`.

        Args:
            cache_file: Path to the metadata cache file. Defaults to
                `metadata_cache.json`.
            log_file: Path to the log file, or None if no log file is
                configured. Defaults to None.
            max_concurrency: Maximum number of concurrent tasks. Defaults to 10.
            report_dir: Path to the directory for recipe reports. Defaults to
                `recipe_reports`.
            verbosity_level: Verbosity level (0, 1, 2, etc.). Defaults to 0.
        """
        if not hasattr(self, "_initialized"):  # Prevent re-initialization
            self._cache_file = cache_file
            self._log_file = log_file
            self._max_concurrency = max_concurrency
            self._report_dir = report_dir
            self._verbosity_level = verbosity_level
            self._initialized = True

    @property
    def cache_file(self) -> Path:
        """Get the cache file path.

        Returns:
            The path to the cache file.
        """
        return self._cache_file

    @cache_file.setter
    def cache_file(self, value: str | Path) -> None:
        """Set the cache file path.

        Args:
            value: The new path to the cache file (either a string or a Path
                object).
        """
        self._cache_file = self._convert_to_path(value)

    @property
    def log_file(self) -> Path | None:
        """Get the log file path.

        Returns:
            The path to the log file, or None if no log file is configured.
        """
        return self._log_file

    @log_file.setter
    def log_file(self, value: str | Path | None) -> None:
        """Set the log file path.

        Args:
            value: The new path to the log file, or None to disable logging
                to a file. Can be either a string or a Path object.
        """
        if value is not None:
            self._log_file = self._convert_to_path(value)
        else:
            self._log_file = None

    @property
    def max_concurrency(self) -> int:
        """Get the maximum concurrency.

        Returns:
            The maximum number of concurrent tasks.
        """
        return self._max_concurrency

    @max_concurrency.setter
    def max_concurrency(self, value: int) -> None:
        """Set the maximum concurrency with validation.

        Args:
            value: The new maximum number of concurrent tasks (an integer).

        Raises:
            SettingsValidationError: If the value is not a positive integer.
        """
        self._validate_integer_is_positive("max_concurrency", value)
        self._max_concurrency = value

    @property
    def report_dir(self) -> Path:
        """Get the report directory.

        Returns:
            The path to the report directory.
        """
        return self._report_dir

    @report_dir.setter
    def report_dir(self, value: str | Path) -> None:
        """Set the report directory.

        Args:
            value: The new path to the report directory (either a string or a
                Path object).
        """
        self._report_dir = self._convert_to_path(value)

    @property
    def verbosity_level(self) -> int:
        """Get the verbosity level.

        Returns:
            The verbosity level.
        """
        return self._verbosity_level

    @verbosity_level.setter
    def verbosity_level(self, value: int) -> None:
        """Set the verbosity level with validation.

        Args:
            value: The new verbosity level (an integer).

        Raises:
            SettingsValidationError: If the value is negative.
        """
        self._validate_integer_is_not_negative("verbosity_level", value)
        self._verbosity_level = value

    def verbosity_int(self, delta: int = 0) -> int:
        """Returns the verbosity level.

        Args:
            delta: An optional integer to add to the base verbosity level.
                This can be used to temporarily increase or decrease the
                verbosity for specific operations.

        Returns:
            The integer verbosity level, adjusted by the delta.
        """
        level = self.verbosity_level + delta
        if level <= 0:
            return 0
        return level

    def verbosity_str(self, delta: int = 0) -> str:
        """Convert an integer verbosity level to a string of `-v` flags.

        Args:
            delta: An optional integer to add to the base verbosity level.
                This can be used to temporarily increase or decrease the
                verbosity for specific operations.

        Returns:
            A string consisting of `-` followed by `v` repeated
            `verbosity_level` times. Returns an empty string if
            verbosity_level is 0 or negative.

        Examples:
            verbosity_str(0) == ""
            verbosity_str(1) == "-v"
            verbosity_str(2) == "-vv"
            verbosity_str(3) == "-vvv"
        """
        level = self.verbosity_level + delta
        if level <= 0:
            return ""
        return "-" + "v" * level

    def _convert_to_path(self, value: str | Path) -> Path:
        """Convert to `pathlib.Path`."""
        if isinstance(value, str):
            return Path(value)
        return value

    def _validate_integer_is_positive(self, field_name: str, value: int) -> None:
        """Validates that an integer value is positive (greater than 0).

        This method checks if the provided integer value is strictly positive.
        If the value is less than 1, a `SettingsValidationError` is raised.

        Args:
            field_name: The name of the setting being validated (used in the
                error message).
            value: The integer value to validate.

        Raises:
            SettingsValidationError: If the value is not a positive integer
                (i.e., it is less than 1).
        """
        if value < 1:
            raise SettingsValidationError(field_name, "Must be a positive integer")

    def _validate_integer_is_not_negative(self, field_name: str, value: int) -> None:
        """Validates that an integer value is not negative (greater than or equal to 0).

        This method checks if the provided integer value is non-negative.
        If the value is less than 0, a `SettingsValidationError` is raised.

        Args:
            field_name: The name of the setting being validated (used in the
                error message).
            value: The integer value to validate.

        Raises:
            SettingsValidationError: If the value is negative (i.e., it is less than 0).
        """
        if value < 0:
            raise SettingsValidationError(field_name, "Must not be negative")


# Create a module-level instance of Settings
settings = SettingsImpl()
