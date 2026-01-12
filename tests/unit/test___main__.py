"""Unit tests for __main__.py."""

import asyncio
import json
import os
import plistlib
import sys
import typing
from argparse import Namespace
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cloud_autopkg_runner import AutoPkgPrefs, ConfigSchema, Recipe, Settings
from cloud_autopkg_runner.__main__ import (
    STOP_WORKER,
    _count_iterable,
    _create_recipe,
    _generate_recipe_list,
    _get_recipe_path,
    _parse_arguments,
    _process_recipe_list,
    _recipe_worker,
    _schema_overrides_from_cli,
)
from cloud_autopkg_runner.exceptions import (
    InvalidFileContents,
    InvalidJsonContents,
    RecipeException,
    RecipeLookupException,
)

if typing.TYPE_CHECKING:
    from collections.abc import Iterable


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


def test_cli_overrides_schema(tmp_path: Path) -> None:
    """Test that CLI arguments correctly override settings via the schema."""
    args = Namespace(
        cache_file="test_cache.json",
        cache_plugin="json",
        log_file=tmp_path / "test_log.txt",
        log_format="json",
        max_concurrency=5,
        recipe_timeout=60,
        report_dir=tmp_path / "test_reports",
        verbose=2,
        pre_processor=["com.example.identifier/preProcessorName"],
        post_processor=["com.example.identifier/postProcessorName"],
        azure_account_url=None,
        cloud_container_name=None,
        autopkg_pref_file=None,
    )

    overrides = _schema_overrides_from_cli(args)
    base_schema = ConfigSchema()
    final_schema = base_schema.with_overrides(overrides)

    settings = Settings()
    settings.load(final_schema)

    assert settings.cache_file == "test_cache.json"
    assert settings.log_file == tmp_path / "test_log.txt"
    assert settings.log_format == "json"
    assert settings.max_concurrency == 5
    assert settings.recipe_timeout == 60
    assert settings.report_dir == tmp_path / "test_reports"
    assert settings.verbosity_level == 2
    assert settings.pre_processors == ["com.example.identifier/preProcessorName"]
    assert settings.post_processors == ["com.example.identifier/postProcessorName"]


def test_generate_recipe_list_from_schema() -> None:
    """Test that _generate_recipe_list correctly reads from the schema."""
    args = Namespace(recipe_list=None, recipe=None)
    schema = ConfigSchema(recipes=["SchemaRecipe1", "SchemaRecipe2"])
    with patch.dict(os.environ, {}, clear=True):
        result = _generate_recipe_list(schema, args)
    assert result == {"SchemaRecipe1", "SchemaRecipe2"}


def test_generate_recipe_list_from_json(tmp_path: Path) -> None:
    """Test that _generate_recipe_list correctly reads from a JSON file."""
    recipe_list_file = tmp_path / "recipes.json"
    recipe_list_file.write_text(json.dumps(["Recipe1", "Recipe2"]))
    args = Namespace(recipe_list=recipe_list_file, recipe=None)
    schema = ConfigSchema(recipes=["Ignored"])  # Should be ignored

    with patch.dict(os.environ, {}, clear=True):
        result = _generate_recipe_list(schema, args)

    assert result == {"Recipe1", "Recipe2"}


def test_generate_recipe_list_from_args() -> None:
    """Test that _generate_recipe_list correctly reads from command-line args."""
    args = Namespace(recipe_list=None, recipe=["Recipe3", "Recipe4"])
    schema = ConfigSchema(recipes=["Ignored"])  # Should be ignored

    with patch.dict(os.environ, {}, clear=True):
        result = _generate_recipe_list(schema, args)

    assert result == {"Recipe3", "Recipe4"}


def test_generate_recipe_list_from_env() -> None:
    """Test that _generate_recipe_list correctly reads from the environment."""
    with patch.dict(os.environ, {"RECIPE": "Recipe5"}):
        args = Namespace(recipe_list=None, recipe=None)
        schema = ConfigSchema()  # No recipes in schema

        result = _generate_recipe_list(schema, args)

        assert result == {"Recipe5"}


def test_generate_recipe_list_combines_sources(tmp_path: Path) -> None:
    """Test that _generate_recipe_list combines CLI and env sources correctly."""
    recipe_list_file = tmp_path / "recipes.json"
    recipe_list_file.write_text(json.dumps(["Recipe1", "Recipe2"]))

    with patch.dict(os.environ, {"RECIPE": "Recipe5"}):
        args = Namespace(recipe_list=recipe_list_file, recipe=["Recipe3", "Recipe4"])
        schema = ConfigSchema(recipes=["Ignored"])  # Should be ignored

        result = _generate_recipe_list(schema, args)

        assert result == {"Recipe1", "Recipe2", "Recipe3", "Recipe4", "Recipe5"}


def test_generate_recipe_list_invalid_json(tmp_path: Path) -> None:
    """Test that _generate_recipe_list raises InvalidJsonContents for bad JSON."""
    recipe_list_file = tmp_path / "recipes.json"
    recipe_list_file.write_text("This is not JSON")
    args = Namespace(recipe_list=recipe_list_file, recipe=None)
    schema = ConfigSchema()

    with pytest.raises(InvalidJsonContents):
        _generate_recipe_list(schema, args)


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
        "--log-format",
        "text",
        "--post-processor",
        "PostProcessor1",
        "--pre-processor",
        "PreProcessor1",
        "--recipe-timeout",
        "60",
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
    assert args.log_format == "text"
    assert args.post_processor == ["PostProcessor1"]
    assert args.pre_processor == ["PreProcessor1"]
    assert args.recipe_timeout == 60
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
        "--log-format=text",
        "--post-processor=PostProcessor1",
        "--pre-processor=PreProcessor1",
        "--recipe-timeout=60",
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
    assert args.log_format == "text"
    assert args.post_processor == ["PostProcessor1"]
    assert args.pre_processor == ["PreProcessor1"]
    assert args.recipe_timeout == 60
    assert args.report_dir == Path("test_reports")
    assert args.max_concurrency == 15


@pytest.mark.asyncio
async def test_create_recipe_success(
    tmp_path: Path, mock_autopkg_prefs: MagicMock
) -> None:
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
        recipe = await _create_recipe("test_recipe", tmp_path, mock_autopkg_prefs)
        assert isinstance(recipe, Recipe)


@pytest.mark.asyncio
async def test_create_recipe_invalid_file_contents(
    tmp_path: Path, mock_autopkg_prefs: MagicMock
) -> None:
    """Should return None and log an error on InvalidFileContents."""
    with (
        patch("cloud_autopkg_runner.__main__.logger") as mock_logger,
        patch(
            "cloud_autopkg_runner.recipe.Recipe",
            side_effect=InvalidFileContents("corrupt recipe file"),
        ),
    ):
        result = await _create_recipe("bad_recipe", tmp_path, mock_autopkg_prefs)

        mock_logger.exception.assert_called_once_with(
            "Failed to create `Recipe` object: %s", "bad_recipe"
        )
        assert result is None


@pytest.mark.asyncio
async def test_create_recipe_recipe_exception(
    tmp_path: Path, mock_autopkg_prefs: MagicMock
) -> None:
    """Should return None and log an error on RecipeException."""
    with (
        patch("cloud_autopkg_runner.__main__.logger") as mock_logger,
        patch(
            "cloud_autopkg_runner.recipe.Recipe",
            side_effect=RecipeException("missing processor"),
        ),
    ):
        result = await _create_recipe("exception_recipe", tmp_path, mock_autopkg_prefs)

        mock_logger.exception.assert_called_once_with(
            "Failed to create `Recipe` object: %s", "exception_recipe"
        )
        assert result is None


@pytest.mark.asyncio
async def test_get_recipe_path_success(
    tmp_path: Path, mock_autopkg_prefs: MagicMock
) -> None:
    """Test that _get_recipe_path returns the correct path to a recipe."""
    recipe_path = tmp_path / "test_recipe.recipe"
    recipe_path.write_text('{"key": "value"}')
    with patch(
        "cloud_autopkg_runner.recipe_finder.RecipeFinder.find_recipe",
        new_callable=AsyncMock,
        return_value=recipe_path,
    ):
        path = await _get_recipe_path("test_recipe", mock_autopkg_prefs)
        assert path == recipe_path


@pytest.mark.asyncio
async def test_get_recipe_path_recipe_lookup_exception(
    mock_autopkg_prefs: MagicMock,
) -> None:
    """Test that _get_recipe_path raises RecipeLookupException."""
    with (
        patch(
            "cloud_autopkg_runner.recipe_finder.RecipeFinder.find_recipe",
            new_callable=AsyncMock,
            side_effect=RecipeLookupException("Recipe not found"),
        ),
        pytest.raises(RecipeLookupException),
    ):
        await _get_recipe_path("test_recipe", mock_autopkg_prefs)


def test_count_iterable_str() -> None:
    """Test that _count_iterable returns the correct value."""
    mock_iterable: Iterable[str] = iter(["foo", "bar", "baz"])
    result = _count_iterable(mock_iterable)

    assert result == 3
    assert type(result) is int


def test_count_iterable_int() -> None:
    """Test that _count_iterable returns the correct value."""
    mock_iterable: Iterable[int] = iter([1, 2, 3])
    result = _count_iterable(mock_iterable)

    assert result == 3
    assert type(result) is int


@pytest.mark.asyncio
async def test_recipe_worker_success(tmp_path: Path) -> None:
    """_recipe_worker should process recipes and return results."""
    queue = asyncio.Queue()
    queue.put_nowait("TestRecipe")
    queue.put_nowait(STOP_WORKER)

    mock_report = MagicMock()
    mock_recipe = MagicMock()
    mock_recipe.name = "TestRecipe"
    mock_recipe.run = AsyncMock(return_value=mock_report)

    mock_settings = MagicMock()
    mock_settings.recipe_timeout = 10
    mock_settings.report_dir = tmp_path

    with patch(
        "cloud_autopkg_runner.__main__._create_recipe",
        new=AsyncMock(return_value=mock_recipe),
    ):
        results = await _recipe_worker(queue, mock_settings, MagicMock())

    assert results == {"TestRecipe": mock_report}
    assert queue.empty()


@pytest.mark.asyncio
async def test_recipe_worker_skips_invalid_recipe(tmp_path: Path) -> None:
    """_recipe_worker should skip when _create_recipe returns None."""
    queue = asyncio.Queue()
    queue.put_nowait("BadRecipe")
    queue.put_nowait(STOP_WORKER)

    mock_settings = MagicMock()
    mock_settings.recipe_timeout = 5
    mock_settings.report_dir = tmp_path

    with patch(
        "cloud_autopkg_runner.__main__._create_recipe", new=AsyncMock(return_value=None)
    ):
        results = await _recipe_worker(queue, mock_settings, MagicMock())

    assert results == {}
    assert queue.empty()


@pytest.mark.asyncio
async def test_recipe_worker_timeout_logged(tmp_path: Path) -> None:
    """TimeoutError during recipe.run() should be logged and skipped."""
    queue = asyncio.Queue()
    queue.put_nowait("TimeoutRecipe")
    queue.put_nowait(STOP_WORKER)

    mock_recipe = MagicMock()
    mock_recipe.name = "TimeoutRecipe"
    mock_recipe.run = AsyncMock(side_effect=TimeoutError())

    mock_settings = MagicMock()
    mock_settings.recipe_timeout = 3
    mock_settings.report_dir = tmp_path

    with (
        patch("cloud_autopkg_runner.__main__.logger") as mock_logger,
        patch(
            "cloud_autopkg_runner.__main__._create_recipe",
            new=AsyncMock(return_value=mock_recipe),
        ),
    ):
        results = await _recipe_worker(queue, mock_settings, MagicMock())

    assert results == {}
    mock_logger.error.assert_called()


@pytest.mark.asyncio
async def test_process_recipe_list_success() -> None:
    """_process_recipe_list should process items and merge worker results."""

    async def fake_worker(
        queue: asyncio.Queue, _settings: Settings, _prefs: AutoPkgPrefs
    ) -> dict[typing.Any, typing.Any]:
        results = {}
        while True:
            item = await queue.get()
            if item is STOP_WORKER:
                queue.task_done()
                break
            results[item] = f"report-{item}"
            queue.task_done()
        return results

    with (
        patch(
            "cloud_autopkg_runner.__main__._recipe_worker",
            new=fake_worker,
        ),
        patch(
            "cloud_autopkg_runner.__main__.get_cache_plugin",
            return_value=AsyncMock().__aenter__.return_value,
        ),
        patch("cloud_autopkg_runner.settings.Settings.max_concurrency", 2),
    ):
        results = await _process_recipe_list(["R1", "R2"], MagicMock())

    assert results == {
        "R1": "report-R1",
        "R2": "report-R2",
    }


@pytest.mark.asyncio
async def test_process_recipe_list_inserts_correct_number_of_stops() -> None:
    """STOP_WORKER should be enqueued exactly once per worker."""
    pushed = []

    class LoggingQueue(asyncio.Queue):
        def put_nowait(self, item: str) -> None:
            pushed.append(item)
            super().put_nowait(item)

    async def fake_worker(
        queue: asyncio.Queue, _settings: Settings, _prefs: AutoPkgPrefs
    ) -> dict[typing.Any, typing.Any]:
        # drain queue to avoid block
        while True:
            item = await queue.get()
            queue.task_done()
            if item is STOP_WORKER:
                break
        return {}

    with (
        patch("cloud_autopkg_runner.__main__.asyncio.Queue", LoggingQueue),
        patch("cloud_autopkg_runner.__main__._recipe_worker", new=fake_worker),
        patch(
            "cloud_autopkg_runner.__main__.get_cache_plugin",
            return_value=AsyncMock().__aenter__.return_value,
        ),
        patch("cloud_autopkg_runner.settings.Settings.max_concurrency", 2),
    ):
        await _process_recipe_list(["A", "B"], MagicMock())

    assert pushed.count(STOP_WORKER) == 2
