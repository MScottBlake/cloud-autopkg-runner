from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest

from cloud_autopkg_runner import AppConfig, list_possible_file_names


@pytest.fixture(autouse=True)
def reset_class_variables() -> Generator[None, Any, None]:
    """Set the class back to default values after each test."""
    yield
    AppConfig._cache_file: Path = Path("metadata_cache.json")
    AppConfig._log_file: Path | None = None
    AppConfig._max_concurrency: int = 10
    AppConfig._report_dir: Path = Path("recipe_reports")
    AppConfig._verbosity_level: int = 0


def test_appconfig_set_config_cache_file() -> None:
    """Tests if a value is set in the config."""
    assert AppConfig.cache_file() == Path("metadata_cache.json")

    AppConfig.set_config(cache_file=Path("cache.json"))
    assert AppConfig.cache_file() == Path("cache.json")


def test_appconfig_set_config_log_file() -> None:
    """Tests if a value is set in the config."""
    assert AppConfig.log_file() is None

    AppConfig.set_config(log_file=Path("log_file.log"))
    assert AppConfig.log_file() == Path("log_file.log")


def test_appconfig_set_config_max_concurrency() -> None:
    """Tests if a value is set in the config."""
    assert AppConfig.max_concurrency() == 10

    AppConfig.set_config(max_concurrency=5)
    assert AppConfig.max_concurrency() == 5


def test_appconfig_set_config_report_dir() -> None:
    """Tests if a value is set in the config."""
    assert AppConfig.report_dir() == Path("recipe_reports")

    AppConfig.set_config(report_dir=Path("new/path"))
    assert AppConfig.report_dir() == Path("new/path")


def test_appconfig_set_config_verbosity_int() -> None:
    """Tests if a value is set in the config."""
    assert AppConfig.verbosity_int() == 0
    assert AppConfig.verbosity_int(2) == 2
    assert AppConfig.verbosity_int(-2) == 0

    AppConfig.set_config(verbosity_level=2)
    assert AppConfig.verbosity_int() == 2
    assert AppConfig.verbosity_int(1) == 3
    assert AppConfig.verbosity_int(-1) == 1


def test_appconfig_set_config_verbosity_str() -> None:
    """Tests if a value is set in the config."""
    assert AppConfig.verbosity_str() == ""
    assert AppConfig.verbosity_str(2) == "-vv"
    assert AppConfig.verbosity_str(-2) == ""

    AppConfig.set_config(verbosity_level=2)
    assert AppConfig.verbosity_str() == "-vv"
    assert AppConfig.verbosity_str(1) == "-vvv"
    assert AppConfig.verbosity_str(-1) == "-v"


def test_appconfig_set_config_multiple() -> None:
    """Tests if a value is set in the config."""
    AppConfig.set_config(
        cache_file=Path("cache.json"),
        log_file=Path("test.log"),
        max_concurrency=10,
        verbosity_level=1,
    )
    assert AppConfig.cache_file() == Path("cache.json")
    assert AppConfig.log_file() == Path("test.log")
    assert AppConfig.max_concurrency() == 10
    assert AppConfig.report_dir() == Path("recipe_reports")
    assert AppConfig.verbosity_int() == 1
    assert AppConfig.verbosity_str() == "-v"


def test_appconfig_initializes_logger() -> None:
    """Test logging initialization."""
    AppConfig.initialize_logger()
    assert AppConfig.log_file() is None


def test_appconfig_initializes_logger_with_file(tmp_path: Path) -> None:
    """Test logging initialization."""
    AppConfig._log_file = tmp_path / "test.log"
    AppConfig.initialize_logger()

    assert AppConfig.log_file() is not None
    assert AppConfig.log_file().exists()


@pytest.mark.parametrize(
    ("recipe_name", "expected_names"),
    [
        (
            "MyRecipe",
            ["MyRecipe.recipe", "MyRecipe.recipe.plist", "MyRecipe.recipe.yaml"],
        ),
        ("MyRecipe.recipe", ["MyRecipe.recipe"]),
        ("MyRecipe.recipe.plist", ["MyRecipe.recipe.plist"]),
        ("MyRecipe.recipe.yaml", ["MyRecipe.recipe.yaml"]),
        (
            "MyRecipe.anything",
            [
                "MyRecipe.anything.recipe",
                "MyRecipe.anything.recipe.plist",
                "MyRecipe.anything.recipe.yaml",
            ],
        ),
    ],
    ids=["no_suffix", "recipe_suffix", "plist_suffix", "yaml_suffix", "random_name"],
)
def test_list_possible_file_names(recipe_name: str, expected_names: list[str]) -> None:
    """Tests list possible file names function based on naming structures.

    This test verifies that the list_possible_file_names function correctly
    generates the expected list of file names for various recipe names,
    including those with and without a file extension, using pytest's
    parameterization feature.
    """
    result = list_possible_file_names(recipe_name)
    assert result == expected_names
