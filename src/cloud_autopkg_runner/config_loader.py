"""Configuration loader for cloud-autopkg-runner.

This module provides a configuration loader that supports:

* Explicit configuration file selection.
* Automatic discovery of configuration sources when no file is provided.
* Full compatibility with both standalone TOML files using
  `[cloud_autopkg_runner]` and `pyproject.toml` files using
  `[tool.cloud_autopkg_runner]`.

The loader parses TOML files using `tomllib` (or `tomli` on Python <3.11) to
ensure compatibility across supported Python versions.
"""

import sys
from pathlib import Path
from typing import Any, TypeAlias

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from cloud_autopkg_runner.exceptions import (
    ConfigFileNotFoundError,
    InvalidConfigFileContentsError,
)

ConfigDict: TypeAlias = dict[str, Any]


class ConfigLoader:
    """Load and normalize configuration for cloud-autopkg-runner.

    A ConfigLoader resolves a single TOML configuration source—either explicitly
    provided by the user or discovered automatically—and extracts the relevant
    configuration table.

    Instances of this class do not mutate global state and are safe for reuse.
    """

    def __init__(self, config_file: str | None = None) -> None:
        """Initialize a ConfigLoader.

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
            self._config_file, self._config_data = self._load_explicit_config(
                Path(config_file),
            )
        else:
            self._config_file, self._config_data = self._discover_config()

    def load(self) -> ConfigDict:
        """Return the loaded configuration.

        Returns:
            A dictionary of configuration values. If no configuration file was
            discovered, an empty dictionary is returned.
        """
        if not self._config_file:
            return {}

        # Return a shallow copy to avoid external mutation
        return self._config_data.copy()

    def _load_explicit_config(
        self,
        path: Path,
    ) -> tuple[Path, ConfigDict]:
        """Load configuration from an explicitly provided file path.

        Args:
            path: Path to the TOML configuration file.

        Returns:
            A tuple of `(path, config_dict)` containing the resolved file path
            and extracted configuration data.

        Raises:
            ConfigFileNotFoundError: If the file does not exist.
            InvalidConfigFileContents: If the file cannot be parsed or does not
                contain the required configuration table.
        """
        if not path.exists():
            raise ConfigFileNotFoundError(path)

        file_path, config = self._load_config_section(path)
        if not file_path or not config:
            raise InvalidConfigFileContentsError(path)

        return file_path, config

    @staticmethod
    def _load_config_section(
        path: Path,
    ) -> tuple[Path | None, ConfigDict]:
        """Parse a TOML file and extract the configuration section.

        This method attempts to parse the TOML file and extract configuration
        from either:

        * `[tool.cloud_autopkg_runner]` (pyproject.toml style), or
        * `[cloud_autopkg_runner]` (standalone config style).

        Args:
            path: Path to the TOML file.

        Returns:
            A tuple `(file_path, config_dict)`. If parsing fails or the required
            configuration table is missing, `(None, {})` is returned.
        """
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError:
            return None, {}

        if "tool" in data:
            return path, data["tool"].get("cloud_autopkg_runner", {})

        return path, data.get("cloud_autopkg_runner", {})

    def _discover_config(self) -> tuple[Path | None, ConfigDict]:
        """Attempt automatic configuration discovery.

        Discovery order:
            1. config.toml
            2. pyproject.toml

        The first file that exists and contains a valid configuration section
        is selected.

        Returns:
            A tuple `(path, config_dict)` where `path` is the resolved
            configuration file and `config_dict` is the extracted section.
            If no suitable file is found, `(None, {})` is returned.
        """
        candidates = (
            Path("config.toml"),
            Path("pyproject.toml"),
        )

        for candidate in candidates:
            if not candidate.exists():
                continue

            file_path, config = self._load_config_section(candidate)
            if file_path and config:
                return file_path, config

        return None, {}
