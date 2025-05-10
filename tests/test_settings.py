"""Tests for the settings module."""

from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from cloud_autopkg_runner import Settings
from cloud_autopkg_runner.exceptions import SettingsValidationError


@pytest.fixture
def settings() -> Generator[Settings, Any, None]:
    """Fixture to get the settings instance.

    Returns:
        Settings: A new instance of the Settings class.
    """
    with patch.object(Settings, "_instance", None):
        instance = Settings()
        yield instance


def test_singleton_pattern() -> None:
    """Verify that the Settings class is a Singleton."""
    settings1 = Settings()
    settings2 = Settings()
    assert settings1 is settings2


def test_attribute_access(settings: Settings) -> None:
    """Test getting and setting each attribute of the Settings class."""
    assert isinstance(settings.cache_file, str)
    assert isinstance(settings.log_file, Path | None)
    assert isinstance(settings.max_concurrency, int)
    assert isinstance(settings.post_processors, list)
    assert isinstance(settings.pre_processors, list)
    assert isinstance(settings.report_dir, Path)
    assert isinstance(settings.verbosity_level, int)


def test_cache_file_setter(settings: Settings) -> None:
    """Test setting the cache_file attribute with a Path object."""
    new_cache_file = "new_cache.json"
    settings.cache_file = new_cache_file
    assert settings.cache_file == new_cache_file


def test_log_file_setter(tmp_path: Path, settings: Settings) -> None:
    """Test setting the log_file attribute with a Path object or None."""
    new_log_file = tmp_path / "new_log.log"
    settings.log_file = new_log_file
    assert settings.log_file == new_log_file

    settings.log_file = str(new_log_file)
    assert settings.log_file == new_log_file

    settings.log_file = None
    assert settings.log_file is None


def test_max_concurrency_setter(settings: Settings) -> None:
    """Test setting the max_concurrency attribute with a valid integer."""
    settings.max_concurrency = 20
    assert settings.max_concurrency == 20


def test_max_concurrency_setter_validation(settings: Settings) -> None:
    """Test setting the max_concurrency attribute with invalid values."""
    with pytest.raises(SettingsValidationError):
        settings.max_concurrency = 0

    with pytest.raises(SettingsValidationError):
        settings.max_concurrency = -1

    with pytest.raises(TypeError):
        settings.max_concurrency = "invalid"


def test_report_dir_setter(tmp_path: Path, settings: Settings) -> None:
    """Test setting the report_dir attribute with a Path object."""
    new_report_dir = tmp_path / "new_reports"
    settings.report_dir = new_report_dir
    assert settings.report_dir == new_report_dir

    settings.report_dir = str(new_report_dir)
    assert settings.report_dir == new_report_dir


def test_verbosity_level_setter(settings: Settings) -> None:
    """Test setting the verbosity_level attribute with a valid integer."""
    settings.verbosity_level = 3
    assert settings.verbosity_level == 3


def test_verbosity_level_setter_validation(settings: Settings) -> None:
    """Test setting the verbosity_level attribute with invalid values."""
    with pytest.raises(SettingsValidationError):
        settings.verbosity_level = -1

    with pytest.raises(TypeError):
        settings.verbosity_level = "invalid"


@pytest.mark.parametrize(
    ("level", "delta", "expected"),
    [
        (0, 0, 0),
        (0, 1, 1),
        (0, 2, 2),
        (0, 3, 3),
        (0, -1, 0),
        (2, 0, 2),
        (2, 1, 3),
        (2, 2, 4),
        (2, 3, 5),
        (2, -1, 1),
        (2, -4, 0),
    ],
)
def test_verbosity_int(
    level: int, delta: int, expected: str, settings: Settings
) -> None:
    """Test the verbosity_str method with different delta values."""
    settings.verbosity_level = level
    assert settings.verbosity_int(delta) == expected


@pytest.mark.parametrize(
    ("level", "delta", "expected"),
    [
        (0, 0, ""),
        (0, 1, "-v"),
        (0, 2, "-vv"),
        (0, 3, "-vvv"),
        (0, -1, ""),
        (2, 0, "-vv"),
        (2, 1, "-vvv"),
        (2, 2, "-vvvv"),
        (2, 3, "-vvvvv"),
        (2, -1, "-v"),
        (2, -4, ""),
    ],
)
def test_verbosity_str(
    level: int, delta: int, expected: str, settings: Settings
) -> None:
    """Test the verbosity_str method with different delta values."""
    settings.verbosity_level = level
    assert settings.verbosity_str(delta) == expected


def test_convert_to_path(settings: Settings) -> None:
    """Test the _convert_to_path method."""
    test_path = Path("/test/path")
    assert settings._convert_to_path("/test/path") == test_path
    assert settings._convert_to_path(test_path) == test_path


@pytest.mark.parametrize(
    ("input_value", "expected_output"),
    [
        ("PreProcessor1", ["PreProcessor1"]),
        ("com.example.test/PreProcessorName", ["com.example.test/PreProcessorName"]),
        (["PreProcessor2", "PreProcessor3"], ["PreProcessor2", "PreProcessor3"]),
        (None, []),
        ("", []),
    ],
)
def test_pre_processors_setter(
    input_value: str | list[str], expected_output: list[str], settings: Settings
) -> None:
    """Test setting the pre_processors attribute with various inputs."""
    settings.pre_processors = input_value
    assert settings.pre_processors == expected_output


@pytest.mark.parametrize(
    ("input_value", "expected_output"),
    [
        ("PostProcessor1", ["PostProcessor1"]),
        ("com.example.test/PostProcessorName", ["com.example.test/PostProcessorName"]),
        (["PostProcessor2", "PostProcessor3"], ["PostProcessor2", "PostProcessor3"]),
        (None, []),
        ("", []),
    ],
)
def test_post_processors_setter(
    input_value: str | list[str], expected_output: list[str], settings: Settings
) -> None:
    """Test setting the post_processors attribute with various inputs."""
    settings.post_processors = input_value
    assert settings.post_processors == expected_output
