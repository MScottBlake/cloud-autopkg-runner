import logging
from pathlib import Path

from cloud_autopkg_runner import AppConfig, list_possible_file_names


def test_appconfig_set_config() -> None:
    """Tests if a value is set in the config."""
    AppConfig.set_config(
        verbosity_level=1,
        log_file="test.log",
        cache_file="cache.json",
        max_concurrency=10,
    )
    assert AppConfig._verbosity_level == 1
    assert AppConfig._log_file == "test.log"
    assert AppConfig._cache_file == Path("cache.json")
    assert AppConfig._max_concurrency == 10


def test_appconfig_initializes_logger(tmp_path: Path) -> None:
    """Test logging initialization."""
    AppConfig._log_file = str(tmp_path / "test.log")
    AppConfig._verbosity_level = 2

    AppConfig.initialize_logger()

    handlers = logging.getLogger().handlers
    assert len(handlers) >= 2

    # Test to see if any file was opened
    if AppConfig._log_file is not None:
        file_exists = Path(AppConfig._log_file).exists()
        assert file_exists

    AppConfig._log_file = None  # Clean up (optional but good practice)
    AppConfig._verbosity_level = 0  # Clear the value after it's being tested.


def test_appconfig_verbosity_string() -> None:
    """Tests the class verbosity and returns a proper -vv string."""
    AppConfig._verbosity_level = 0
    assert AppConfig.verbosity_str() == ""

    AppConfig._verbosity_level = 2
    assert AppConfig.verbosity_str() == "-vv"


def test_list_possible_file_names() -> None:
    """Tests list possible file names function based on naming structures."""
    recipe_name = "MyRecipe"
    expected_names = [
        "MyRecipe.recipe",
        "MyRecipe.recipe.plist",
        "MyRecipe.recipe.yaml",
    ]
    result = list_possible_file_names(recipe_name)
    assert result == expected_names

    # Test with existing file endings
    recipe_name = "MyRecipe.recipe.plist"
    expected_names = ["MyRecipe.recipe.plist"]
    result = list_possible_file_names(recipe_name)
    assert result == expected_names
