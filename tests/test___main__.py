"""Unit tests for __main__.py."""

import json
import os
import plistlib
import sys
from argparse import Namespace
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cloud_autopkg_runner import AutoPkgPrefs, Recipe, Settings
from cloud_autopkg_runner.__main__ import (
    _apply_args_to_settings,
    _create_recipe,
    _generate_recipe_list,
    _get_recipe_path,
    _parse_arguments,
)
from cloud_autopkg_runner.exceptions import (
    InvalidFileContents,
    InvalidJsonContents,
    RecipeException,
    RecipeLookupException,
)


@pytest.fixture
def settings() -> Settings:
    """Fixture to get the settings instance.

    Returns:
        Settings: A new instance of the Settings class.
    """
    with patch.object(Settings, "_instance", None):
        instance = Settings()
        yield instance


@pytest.fixture
def mock_autopkg_prefs(tmp_path: Path) -> MagicMock:
    """Fixture to create a mock AutoPkgPrefs object with search/override dirs.

    Returns:
        MagicMock: A mock AutoPkgPrefs object.
    """
    mock_prefs = MagicMock(spec=AutoPkgPrefs)
    mock_prefs.recipe_override_dirs = [tmp_path]
    mock_prefs.recipe_search_dirs = [tmp_path]
    return mock_prefs


def test_apply_args_to_settings(tmp_path: Path, settings: Settings) -> None:
    """Test that _apply_args_to_settings correctly sets settings."""
    args = Namespace(
        cache_file="test_cache.json",
        cache_plugin="json",
        log_file=tmp_path / "test_log.txt",
        max_concurrency=5,
        report_dir=tmp_path / "test_reports",
        verbose=2,
    )

    _apply_args_to_settings(args)

    assert settings.cache_file == "test_cache.json"
    assert Path(settings.cache_file) == Path("test_cache.json")
    assert tmp_path / settings.cache_file == tmp_path / "test_cache.json"
    assert settings.log_file == tmp_path / "test_log.txt"
    assert settings.max_concurrency == 5
    assert settings.report_dir == tmp_path / "test_reports"
    assert settings.verbosity_level == 2


def test_generate_recipe_list_from_json(tmp_path: Path) -> None:
    """Test that _generate_recipe_list correctly reads from a JSON file."""
    recipe_list_file = tmp_path / "recipes.json"
    recipe_list_file.write_text(json.dumps(["Recipe1", "Recipe2"]))
    args = Namespace(recipe_list=recipe_list_file, recipe=None)

    result = _generate_recipe_list(args)

    assert result == {"Recipe1", "Recipe2"}


def test_generate_recipe_list_from_args() -> None:
    """Test that _generate_recipe_list correctly reads from command-line args."""
    args = Namespace(recipe_list=None, recipe=["Recipe3", "Recipe4"])

    result = _generate_recipe_list(args)

    assert result == {"Recipe3", "Recipe4"}


def test_generate_recipe_list_from_env() -> None:
    """Test that _generate_recipe_list correctly reads from the environment."""
    with patch.dict(os.environ, {"RECIPE": "Recipe5"}):
        args = Namespace(recipe_list=None, recipe=None)

        result = _generate_recipe_list(args)

        assert result == {"Recipe5"}


def test_generate_recipe_list_combines_sources(tmp_path: Path) -> None:
    """Test that _generate_recipe_list combines all sources correctly."""
    recipe_list_file = tmp_path / "recipes.json"
    recipe_list_file.write_text(json.dumps(["Recipe1", "Recipe2"]))

    with patch.dict(os.environ, {"RECIPE": "Recipe5"}):
        args = Namespace(recipe_list=recipe_list_file, recipe=["Recipe3", "Recipe4"])

        result = _generate_recipe_list(args)

        assert result == {"Recipe1", "Recipe2", "Recipe3", "Recipe4", "Recipe5"}


def test_generate_recipe_list_invalid_json(tmp_path: Path) -> None:
    """Test that _generate_recipe_list raises InvalidJsonContents for bad JSON."""
    recipe_list_file = tmp_path / "recipes.json"
    recipe_list_file.write_text("This is not JSON")
    args = Namespace(recipe_list=recipe_list_file, recipe=None)

    with pytest.raises(InvalidJsonContents):
        _generate_recipe_list(args)


def test_parse_arguments() -> None:
    """Test that the correct arguments are returned."""
    # Simulate command-line arguments
    testargs = [
        "__main__.py",
        "-v",
        "-v",
        "-r",
        "Recipe1",
        "-r",
        "Recipe2",
        "--recipe-list",
        "recipes.json",
        "--cache-file",
        "test_cache.json",
        "--log-file",
        "test_log.txt",
        "--post-processor",
        "PostProcessor1",
        "--pre-processor",
        "PreProcessor1",
        "--report-dir",
        "test_reports",
        "--max-concurrency",
        "15",
    ]
    with patch.object(sys, "argv", testargs):
        args = _parse_arguments()

    assert args.verbose == 2
    assert args.recipe == ["Recipe1", "Recipe2"]
    assert args.recipe_list == Path("recipes.json")
    assert args.cache_file == "test_cache.json"
    assert args.log_file == Path("test_log.txt")
    assert args.post_processor == ["PostProcessor1"]
    assert args.pre_processor == ["PreProcessor1"]
    assert args.report_dir == Path("test_reports")
    assert args.max_concurrency == 15


def test_parse_arguments_diff_syntax() -> None:
    """Test that the correct arguments are returned."""
    # Simulate command-line arguments
    testargs = [
        "__main__.py",
        "-vv",
        "-r=Recipe1",
        "-r=Recipe2",
        "--recipe-list=recipes.json",
        "--cache-file=test_cache.json",
        "--log-file=test_log.txt",
        "--post-processor=PostProcessor1",
        "--pre-processor=PreProcessor1",
        "--report-dir=test_reports",
        "--max-concurrency=15",
    ]
    with patch.object(sys, "argv", testargs):
        args = _parse_arguments()

    assert args.verbose == 2
    assert args.recipe == ["Recipe1", "Recipe2"]
    assert args.recipe_list == Path("recipes.json")
    assert args.cache_file == "test_cache.json"
    assert args.log_file == Path("test_log.txt")
    assert args.post_processor == ["PostProcessor1"]
    assert args.pre_processor == ["PreProcessor1"]
    assert args.report_dir == Path("test_reports")
    assert args.max_concurrency == 15


@pytest.mark.asyncio
async def test_create_recipe_success(tmp_path: Path) -> None:
    """Test that _create_recipe successfully creates a Recipe object."""
    plist_content = {
        "Description": "Test recipe",
        "Identifier": "com.example.test",
        "Input": {"NAME": "TestRecipe"},
        "Process": [],
        "MinimumVersion": "",
        "ParentRecipe": "",
    }
    recipe_path = tmp_path / "test_recipe.recipe"
    recipe_path.write_bytes(plistlib.dumps(plist_content))
    mock_get_recipe_path = AsyncMock(return_value=recipe_path)
    with patch(
        "cloud_autopkg_runner.__main__._get_recipe_path", new=mock_get_recipe_path
    ):
        recipe = await _create_recipe("test_recipe")
        assert isinstance(recipe, Recipe)


@pytest.mark.asyncio
async def test_create_recipe_invalid_file_contents(
    mock_autopkg_prefs: MagicMock,
) -> None:
    """Should return None and log an error on InvalidFileContents."""
    with (
        patch(
            "cloud_autopkg_runner.recipe_finder.AutoPkgPrefs",
            return_value=mock_autopkg_prefs,
        ),
        patch("cloud_autopkg_runner.logging_config.get_logger") as mock_get_logger,
        patch(
            "cloud_autopkg_runner.recipe.Recipe",
            side_effect=InvalidFileContents("corrupt recipe file"),
        ),
    ):
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        result = await _create_recipe("bad_recipe")

        mock_logger.exception.assert_called_once_with(
            "Failed to create recipe: %s", "bad_recipe"
        )
        assert result is None


@pytest.mark.asyncio
async def test_create_recipe_recipe_exception(mock_autopkg_prefs: MagicMock) -> None:
    """Should return None and log an error on RecipeException."""
    with (
        patch(
            "cloud_autopkg_runner.recipe_finder.AutoPkgPrefs",
            return_value=mock_autopkg_prefs,
        ),
        patch("cloud_autopkg_runner.logging_config.get_logger") as mock_get_logger,
        patch(
            "cloud_autopkg_runner.recipe.Recipe",
            side_effect=RecipeException("missing processor"),
        ),
    ):
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        result = await _create_recipe("exception_recipe")

        mock_logger.exception.assert_called_once_with(
            "Failed to create recipe: %s", "exception_recipe"
        )
        assert result is None


@pytest.mark.asyncio
async def test_get_recipe_path_success(
    tmp_path: Path, mock_autopkg_prefs: MagicMock
) -> None:
    """Test that _get_recipe_path returns the correct path to a recipe."""
    recipe_path = tmp_path / "test_recipe.recipe"
    recipe_path.write_text('{"key": "value"}')
    with (
        patch(
            "cloud_autopkg_runner.recipe_finder.AutoPkgPrefs",
            return_value=mock_autopkg_prefs,
        ),
        patch(
            "cloud_autopkg_runner.recipe_finder.RecipeFinder.find_recipe",
            new_callable=AsyncMock,
            return_value=recipe_path,
        ),
    ):
        path = await _get_recipe_path("test_recipe")
        assert path == recipe_path


@pytest.mark.asyncio
async def test_get_recipe_path_recipe_lookup_exception(
    mock_autopkg_prefs: MagicMock,
) -> None:
    """Test that _get_recipe_path raises RecipeLookupException."""
    with (
        patch(
            "cloud_autopkg_runner.recipe_finder.AutoPkgPrefs",
            return_value=mock_autopkg_prefs,
        ),
        patch(
            "cloud_autopkg_runner.recipe_finder.RecipeFinder.find_recipe",
            new_callable=AsyncMock,
            side_effect=RecipeLookupException("Recipe not found"),
        ),
        pytest.raises(RecipeLookupException),
    ):
        await _get_recipe_path("test_recipe")
