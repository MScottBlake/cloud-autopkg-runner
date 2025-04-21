"""Unit tests for __main__.py."""

import json
import os
import sys
from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cloud_autopkg_runner import settings
from cloud_autopkg_runner.__main__ import (
    _apply_args_to_settings,
    _create_recipe,
    _generate_recipe_list,
    _parse_arguments,
)
from cloud_autopkg_runner.exceptions import (
    InvalidFileContents,
    InvalidJsonContents,
    RecipeException,
)


def test_apply_args_to_settings(tmp_path: Path) -> None:
    """Test that _apply_args_to_settings correctly sets settings."""
    args = Namespace(
        cache_file=tmp_path / "test_cache.json",
        log_file=tmp_path / "test_log.txt",
        max_concurrency=5,
        report_dir=tmp_path / "test_reports",
        verbose=2,
    )

    _apply_args_to_settings(args)

    assert settings.cache_file == tmp_path / "test_cache.json"
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
    assert args.cache_file == Path("test_cache.json")
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
    assert args.cache_file == Path("test_cache.json")
    assert args.log_file == Path("test_log.txt")
    assert args.post_processor == ["PostProcessor1"]
    assert args.pre_processor == ["PreProcessor1"]
    assert args.report_dir == Path("test_reports")
    assert args.max_concurrency == 15


@pytest.mark.asyncio
async def test_create_recipe_success() -> None:
    """Should return a Recipe object when creation succeeds."""
    with (
        patch("cloud_autopkg_runner.__main__.Recipe") as mock_recipe,
        patch("cloud_autopkg_runner.__main__.settings") as mock_settings,
    ):
        mock_settings.report_dir = "/mock/report_dir"
        mock_instance = MagicMock()
        mock_recipe.return_value = mock_instance

        result = await _create_recipe("good_recipe")

        mock_recipe.assert_called_once_with("good_recipe", "/mock/report_dir")
        assert result == mock_instance


@pytest.mark.asyncio
async def test_create_recipe_invalid_file_contents() -> None:
    """Should return None and log an error on InvalidFileContents."""
    with (
        patch("cloud_autopkg_runner.__main__.get_logger") as mock_get_logger,
        patch(
            "cloud_autopkg_runner.__main__.Recipe",
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
async def test_create_recipe_recipe_exception() -> None:
    """Should return None and log an error on RecipeException."""
    with (
        patch("cloud_autopkg_runner.__main__.get_logger") as mock_get_logger,
        patch(
            "cloud_autopkg_runner.__main__.Recipe",
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
