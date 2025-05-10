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

from cloud_autopkg_runner.exceptions import SettingsValidationError


class Settings:
    """Manages application settings using properties and custom setters.

    Ensures only one instance is available globally. Provides type-safe
    access and validation for setting application configurations.

    Attributes:
        _instance: The singleton instance of the Settings class.
    """

    _instance: "Settings | None" = None

    def __new__(cls) -> "Settings":
        """Create a new instance of Settings if one doesn't exist.

        This `__new__` method implements the Singleton pattern, ensuring
        that only one instance of the `Settings` class is ever created.
        If an instance already exists, it is returned; otherwise, a new
        instance is created and stored for future use.

        Returns:
            The Settings instance.
        """
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize the application settings.

        Sets the default values for the application settings. This method
        is called only once due to the Singleton pattern implemented in
        `__new__`.
        """
        if hasattr(self, "_initialized"):
            return  # Prevent re-initialization

        self._log_file: Path | None = None
        self._max_concurrency: int = 10
        self._post_processors: list[str] = []
        self._pre_processors: list[str] = []
        self._report_dir: Path = Path("recipe_reports")
        self._verbosity_level: int = 0

        self._cache_plugin: str = "default"
        self._cache_file: str = "metadata_cache.json"

        self._initialized = True

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
        """
        self._validate_integer_is_positive("max_concurrency", value)
        self._max_concurrency = value

    @property
    def post_processors(self) -> list[str]:
        """Get the list of post-processors.

        Returns:
            The list of post-processors.
        """
        return self._post_processors

    @post_processors.setter
    def post_processors(self, value: str | list[str]) -> None:
        """Set the post-processor list.

        Args:
            value: The new list of post-processors (either a string or a
                list of strings).
        """
        if not value:
            self._post_processors = []
        elif isinstance(value, str):
            self._post_processors = [value]
        else:
            self._post_processors = value

    @property
    def pre_processors(self) -> list[str]:
        """Get the list of pre-processors.

        Returns:
            The list of pre-processors, or None if no pre-processor is configured.
        """
        return self._pre_processors

    @pre_processors.setter
    def pre_processors(self, value: str | list[str]) -> None:
        """Set the pre-processor list.

        Args:
            value: The new list of pre-processors (either a string or a
                list of strings).
        """
        if not value:
            self._pre_processors = []
        elif isinstance(value, str):
            self._pre_processors = [value]
        else:
            self._pre_processors = value

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

    @staticmethod
    def _convert_to_path(value: str | Path) -> Path:
        """Convert to `pathlib.Path`.

        Args:
            value: The value to convert to a `Path` object (either a string or a `Path`
            object).

        Returns:
            A `Path` object representing the given value.
        """
        if isinstance(value, str):
            return Path(value)
        return value

    @staticmethod
    def _validate_integer_is_positive(field_name: str, value: int) -> None:
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

    @staticmethod
    def _validate_integer_is_not_negative(field_name: str, value: int) -> None:
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

    # Plugin Properties

    @property
    def cache_plugin(self) -> str:
        """Get the cache file plugin.

        Returns:
            The name of the cache plugin.
        """
        return self._cache_plugin or "default"

    @cache_plugin.setter
    def cache_plugin(self, value: str) -> None:
        """Set the cache plugin.

        Args:
            value: The cache plugin to use.
        """
        self._cache_plugin = value

    @property
    def cache_file(self) -> str:
        """Get the cache file path.

        Returns:
            The path to the cache file.
        """
        return self._cache_file

    @cache_file.setter
    def cache_file(self, value: str) -> None:
        """Set the cache file path.

        Args:
            value: The new path to the cache file (either a string or a Path
                object).
        """
        self._cache_file = value

    @property
    def azure_account_url(self) -> str:
        """Get the Azure Account URL.

        Returns:
            The URL of the Azure Account.
        """
        return self._azure_account_url

    @azure_account_url.setter
    def azure_account_url(self, value: str) -> None:
        """Set the Azure Account URL.

        Args:
            value: The URL of the Azure Account.
        """
        self._azure_account_url = value

    @property
    def cloud_container_name(self) -> str:
        """Get the container name.

        Returns:
            The name of the container.
        """
        return self._cloud_container_name

    @cloud_container_name.setter
    def cloud_container_name(self, value: str) -> None:
        """Set the container name.

        Args:
            value: The name of the container.
        """
        self._cloud_container_name = value
