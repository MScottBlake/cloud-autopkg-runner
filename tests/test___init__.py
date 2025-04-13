import logging
from pathlib import Path

import pytest

from cloud_autopkg_runner import AppConfig, list_possible_file_names


def test_appconfig_set_config() -> None:
    """Tests if a value is set in the config."""
    AppConfig.set_config(
        verbosity_level=1,
        log_file=Path("test.log"),
        cache_file=Path("cache.json"),
        max_concurrency=10,
    )
    assert AppConfig._verbosity_level == 1
    assert AppConfig._log_file == Path("test.log")
    assert AppConfig._cache_file == Path("cache.json")
    assert AppConfig._max_concurrency == 10


def test_appconfig_initializes_logger(tmp_path: Path) -> None:
    """Test logging initialization."""
    AppConfig._log_file = tmp_path / "test.log"
    AppConfig._verbosity_level = 2

    AppConfig.initialize_logger()

    handlers = logging.getLogger().handlers
    assert len(handlers) >= 2

    # Test to see if any file was opened
    if AppConfig._log_file is not None:
        file_exists = AppConfig._log_file.exists()
        assert file_exists

    AppConfig._log_file = None  # Clean up (optional but good practice)
    AppConfig._verbosity_level = 0  # Clear the value after it's being tested.


def test_appconfig_verbosity_string() -> None:
    """Tests the class verbosity and returns a proper -vv string."""
    AppConfig._verbosity_level = 0
    assert AppConfig.verbosity_str() == ""

    AppConfig._verbosity_level = 2
    assert AppConfig.verbosity_str() == "-vv"


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
