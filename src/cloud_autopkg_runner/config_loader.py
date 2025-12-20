"""Configuration loader for cloud-autopkg-runner.

This module provides a high-cohesion, low-coupling configuration loader that
supports:

* Explicit configuration file selection.
* Automatic discovery of configuration sources when no file is provided.
* Recursive deep-merging of context-specific override files.
* Full compatibility with both standalone TOML files using
  `[cloud_autopkg_runner]` and `pyproject.toml` files using
  `[tool.cloud_autopkg_runner]`.

The loader parses TOML files using `tomllib` (or `tomli` on Python <3.11) to
ensure compatibility across supported Python versions.

Design Principles:
    - High Cohesion: Discovery, parsing, and merging are isolated into narrowly
      scoped functions.
    - Low Coupling: `load()` never interacts with the file system directly;
      discovery and extraction are delegated to helpers.
    - Law of Demeter: Each method only interacts with its immediate
      collaborators (paths, dictionaries, or internal helpers).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

from cloud_autopkg_runner import logging_config
from cloud_autopkg_runner.exceptions import (
    ConfigFileNotFoundError,
    InvalidConfigFileContents,
)


class ConfigLoader:
    """Load, normalize, and merge configuration for cloud-autopkg-runner.

    A ConfigLoader resolves the correct TOML configuration source and extracts
    the relevant configuration options. It optionally applies context overlays
    from files named `<base_stem>.<context>.toml`, merging them recursively such
    that context values override base values.

    Instances of this class do not mutate global state and are safe for use in
    parallel workflows.
    """

    def __init__(self, config_file: str | None = None) -> None:
        """Initialize a ConfigLoader and prepare base configuration.

        Args:
            config_file: Optional TOML file path explicitly provided by the
                user. If supplied, the file must exist and contain the required
                configuration table.

        Raises:
            ConfigFileNotFoundError: If an explicit config file path does not exist.
            InvalidConfigFileContents: If the file exists but does not contain
                a valid configuration table or cannot be parsed.
        """
        if config_file:
            path = Path(config_file)

            if not path.exists():
                raise ConfigFileNotFoundError(path)

            file, base_data = self._try_load_and_extract(path)
            if base_data == {}:
                raise InvalidConfigFileContents(path)

            self._config_file = file
            self._base_data = base_data
        else:
            file, base_data = self._discover_config()
            self._config_file = file
            self._base_data = base_data

    @staticmethod
    def _try_load_and_extract(path: Path) -> tuple[Path | None, dict[str, Any]]:
        """Attempt to parse a TOML file and extract configuration.

        This helper reads a TOML file, parses it, and extracts the appropriate
        configuration table. Files that fail to parse or lack the required
        configuration section are treated as invalid.

        Args:
            path: Path to the TOML file.

        Returns:
            A tuple `(file_path, config_dict)`. If parsing fails or no relevant
            configuration table exists, the tuple `(None, {})` is returned.
        """
        try:
            data = tomllib.loads(path.read_text())
        except tomllib.TOMLDecodeError:
            return None, {}

        if "tool" in data:
            return path, data["tool"].get("cloud_autopkg_runner", {})

        return path, data.get("cloud_autopkg_runner", {})

    def _discover_config(self) -> tuple[Path | None, dict[str, Any]]:
        """Attempt automatic configuration discovery.

        Discovery order:
            1. config.toml
            2. pyproject.toml

        The first file that exists and contains a valid configuration section
        is selected as the base configuration source.

        Returns:
            A tuple `(path, config_dict)` where `path` is the resolved
            configuration file and `config_dict` is the extracted section.
            If no suitable file is found, `(None, {})` is returned.
        """
        candidates = [
            Path("config.toml"),
            Path("pyproject.toml"),
        ]

        for candidate in candidates:
            if not candidate.exists():
                continue

            file, config = self._try_load_and_extract(candidate)
            if file and config:
                return file, config

        return None, {}

    def _deep_merge(
        self,
        base: dict[str, Any],
        override: dict[str, Any],
    ) -> dict[str, Any]:
        """Recursively merge two dictionaries.

        Dictionaries are merged deeply: for keys where both values are dicts,
        merging continues recursively. Non-dict values in the override always
        replace those in the base.

        Args:
            base: The base configuration dictionary.
            override: A dictionary whose values override those in `base`.

        Returns:
            A new dictionary containing the merged configuration.
        """
        result: dict[str, Any] = base.copy()

        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = self._deep_merge(result[key], value)  # pyright: ignore[reportUnknownArgumentType]
            else:
                result[key] = value

        return result

    def load(self, context: str | None = None) -> dict[str, Any]:
        """Load configuration and apply a context overlay when applicable.

        Context overlays are only supported for standalone configuration files
        (not for pyproject.toml). A context file named
        `<base_stem>.<context>.toml` is loaded when available, and its values
        override the base configuration recursively.

        Args:
            context: Optional context name (e.g., "dev", "prod"). If `None`,
                only the base configuration is used.

        Returns:
            A dictionary of configuration settings. If no configuration file is
            discovered, an empty dictionary is returned.

        Raises:
            InvalidConfigFileContents: If a context TOML file exists but cannot
                be parsed.
        """
        if not self._config_file:
            return {}

        base = self._base_data

        # pyproject.toml does not support context overlays
        if not context or self._config_file.name == "pyproject.toml":
            return base

        context_path = Path(f"{self._config_file.stem}.{context}.toml")
        file, ctx = self._try_load_and_extract(context_path)

        if not file:
            logger = logging_config.get_logger(__name__)
            logger.warning("Context file '%s' not found. Skipping.", context_path)
            return base

        return self._deep_merge(base, ctx)
