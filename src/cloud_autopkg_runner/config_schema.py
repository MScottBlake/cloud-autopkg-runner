"""Configuration schema definitions.

This module defines the canonical configuration schema for
cloud-autopkg-runner. The schema represents the complete set of
supported configuration options, their types, and default values.

The schema is intentionally immutable and side-effect free. It is
used as an intermediate representation between raw configuration
data (files, CLI, environment) and validated runtime settings.
"""

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from cloud_autopkg_runner.exceptions import InvalidConfigurationKeyError


@dataclass(frozen=True, slots=True)
class ConfigSchema:
    """Canonical configuration schema.

    This class defines all supported configuration options along with
    their default values. It does not perform validation or IO and
    should be treated as an immutable value object.
    """

    # Logging
    log_file: Path | None = None
    log_format: str | None = None
    verbosity_level: int | None = None

    # Execution
    max_concurrency: int | None = None
    recipe_timeout: int | None = None
    report_dir: Path | None = None
    recipes: list[str] | None = None
    input_variables: dict[str, str] | None = None

    # Cache
    cache_plugin: str | None = None
    cache_file: str | None = None
    cloud_container_name: str | None = None
    azure_account_url: str | None = None

    # Processors
    pre_processors: list[str] | None = None
    post_processors: list[str] | None = None

    # AutoPkg
    autopkg_pref_file: Path | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConfigSchema":
        """Create a configuration schema from normalized mapping data.

        Args:
            data: A dictionary produced by `ConfigLoader` containing
                normalized configuration values.

        Returns:
            A `ConfigSchema` instance populated with values from the mapping.

        Raises:
            InvalidConfigurationKeyError: If the mapping contains unsupported keys.
        """
        try:
            return cls(**data)
        except TypeError as exc:
            raise InvalidConfigurationKeyError from exc

    def with_overrides(self, overrides: dict[str, Any]) -> "ConfigSchema":
        """Return a new schema with the provided overrides applied.

        Args:
            overrides: A mapping of schema field names to override values.

        Returns:
            A new `ConfigSchema` instance with overrides applied.

        Raises:
            InvalidConfigurationKeyError: If overrides contain unsupported keys.
        """
        try:
            return replace(self, **overrides)
        except TypeError as exc:
            raise InvalidConfigurationKeyError from exc
