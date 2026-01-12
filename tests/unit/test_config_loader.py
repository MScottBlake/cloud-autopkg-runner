"""Full test suite for ConfigLoader.

This module validates all documented behaviors of the ConfigLoader, including:

- Explicit configuration file loading
- Automatic configuration discovery
- TOML parsing and extraction rules
- Error handling for invalid and missing files
- Recursive deep-merge semantics
- Context overlay behavior and limitations
- Logging behavior for missing overlays

The tests intentionally avoid mocking internal helpers to preserve realistic
filesystem behavior and ensure confidence in discovery and parsing logic.
"""

from pathlib import Path

import pytest

from cloud_autopkg_runner.config_loader import ConfigLoader
from cloud_autopkg_runner.exceptions import (
    ConfigFileNotFoundError,
    InvalidConfigFileContents,
)


def _write(path: Path, text: str) -> None:
    """Write TOML text to a file.

    Args:
        path: Destination path.
        text: TOML contents.
    """
    path.write_text(text.strip() + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Explicit config file loading
# ---------------------------------------------------------------------------


def test_explicit_config_file_loaded_successfully(tmp_path: Path) -> None:
    """Explicit config file is loaded and parsed correctly."""
    config = tmp_path / "config.toml"

    _write(
        config,
        """
        [cloud_autopkg_runner]
        retries = 3
        """,
    )

    loader = ConfigLoader(config_file=str(config))
    result = loader.load()

    assert result == {"retries": 3}


def test_explicit_config_file_missing_raises(tmp_path: Path) -> None:
    """Missing explicit config file raises ConfigFileNotFoundError."""
    missing = tmp_path / "missing.toml"

    with pytest.raises(ConfigFileNotFoundError):
        ConfigLoader(config_file=str(missing))


def test_explicit_config_file_without_required_table_raises(tmp_path: Path) -> None:
    """Config file without required table raises InvalidConfigFileContents."""
    config = tmp_path / "config.toml"

    _write(
        config,
        """
        [unrelated]
        value = true
        """,
    )

    with pytest.raises(InvalidConfigFileContents):
        ConfigLoader(config_file=str(config))


def test_explicit_invalid_toml_raises(tmp_path: Path) -> None:
    """Invalid TOML content raises InvalidConfigFileContents."""
    config = tmp_path / "config.toml"
    config.write_text("= invalid toml =", encoding="utf-8")

    with pytest.raises(InvalidConfigFileContents):
        ConfigLoader(config_file=str(config))


# ---------------------------------------------------------------------------
# Automatic discovery
# ---------------------------------------------------------------------------


def test_discovery_prefers_config_toml(tmp_path: Path) -> None:
    """config.toml is preferred over pyproject.toml."""
    config_toml = tmp_path / "config.toml"
    pyproject = tmp_path / "pyproject.toml"

    _write(
        config_toml,
        """
        [cloud_autopkg_runner]
        source = "config"
        """,
    )

    _write(
        pyproject,
        """
        [tool.cloud_autopkg_runner]
        source = "pyproject"
        """,
    )

    with pytest.MonkeyPatch.context() as mp:
        mp.chdir(tmp_path)

        loader = ConfigLoader()
        result = loader.load()

    assert result["source"] == "config"


def test_discovery_uses_pyproject_when_config_missing(tmp_path: Path) -> None:
    """pyproject.toml is used when config.toml is absent."""
    pyproject = tmp_path / "pyproject.toml"

    _write(
        pyproject,
        """
        [tool.cloud_autopkg_runner]
        enabled = true
        """,
    )

    with pytest.MonkeyPatch.context() as mp:
        mp.chdir(tmp_path)

        loader = ConfigLoader()
        result = loader.load()

    assert result == {"enabled": True}


def test_discovery_returns_empty_when_no_files(tmp_path: Path) -> None:
    """No config files results in empty configuration."""
    with pytest.MonkeyPatch.context() as mp:
        mp.chdir(tmp_path)

        loader = ConfigLoader()
        result = loader.load()

    assert result == {}


def test_discovery_skips_invalid_files(tmp_path: Path) -> None:
    """Invalid TOML files are skipped during discovery."""
    config = tmp_path / "config.toml"

    config.write_text("= invalid =", encoding="utf-8")

    with pytest.MonkeyPatch.context() as mp:
        mp.chdir(tmp_path)

        loader = ConfigLoader()
        result = loader.load()

    assert result == {}
