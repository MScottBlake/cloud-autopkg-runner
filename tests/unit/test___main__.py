"""Unit tests for __main__.py."""

import asyncio
import json
import os
import plistlib
import sys
import typing
from argparse import ArgumentTypeError, Namespace
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cloud_autopkg_runner import AutoPkgPrefs, ConfigSchema, Recipe, Settings
from cloud_autopkg_runner.__main__ import (
    EXIT_FAILURE,
    EXIT_SUCCESS,
    STOP_WORKER,
    _async_main,
    _create_recipe,
    _generate_recipe_list,
    _get_recipe_path,
    _key_value_pair,
    _log_run_summary,
    _parse_arguments,
    _process_recipe_list,
    _recipe_worker,
    _schema_overrides_from_cli,
    main,
)
from cloud_autopkg_runner.exceptions import (
    InvalidFileContentsError,
    InvalidJsonContentsError,
    RecipeError,
    RecipeLookupError,
)
from cloud_autopkg_runner.recipe_report import ConsolidatedReport, RunResults


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
        autopkg_path=Path("/opt/homebrew/bin/autopkg"),
        autopkg_pref_file=None,
        key=[("KEY1", "VALUE1"), ("KEY2", "VALUE2")],
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
    assert settings.input_variables == {"KEY1": "VALUE1", "KEY2": "VALUE2"}
    assert settings.autopkg_path == Path("/opt/homebrew/bin/autopkg")


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
    """Test that _generate_recipe_list raises InvalidJsonContentsError for bad JSON."""
    recipe_list_file = tmp_path / "recipes.json"
    recipe_list_file.write_text("This is not JSON")
    args = Namespace(recipe_list=recipe_list_file, recipe=None)
    schema = ConfigSchema()

    with pytest.raises(InvalidJsonContentsError):
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
        "--key",
        "KEY1=VALUE1",
        "--key",
        "KEY2=VALUE2",
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
    assert args.key == [("KEY1", "VALUE1"), ("KEY2", "VALUE2")]


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
        "--key=KEY1=VALUE1",
        "--key=KEY2=VALUE2",
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
    assert args.key == [("KEY1", "VALUE1"), ("KEY2", "VALUE2")]


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
    """Should return None and log an error on InvalidFileContentsError."""
    with (
        patch("cloud_autopkg_runner.__main__.logger") as mock_logger,
        patch(
            "cloud_autopkg_runner.recipe.Recipe",
            side_effect=InvalidFileContentsError("corrupt recipe file"),
        ),
    ):
        result = await _create_recipe("bad_recipe", tmp_path, mock_autopkg_prefs)

        mock_logger.error.assert_called_once()
        assert mock_logger.error.call_args.args[1] == "bad_recipe"
        assert result is None


@pytest.mark.asyncio
async def test_create_recipe_recipe_error(
    tmp_path: Path, mock_autopkg_prefs: MagicMock
) -> None:
    """Should return None and log an error on RecipeError."""
    with (
        patch("cloud_autopkg_runner.__main__.logger") as mock_logger,
        patch(
            "cloud_autopkg_runner.recipe.Recipe",
            side_effect=RecipeError("missing processor"),
        ),
    ):
        result = await _create_recipe("error_recipe", tmp_path, mock_autopkg_prefs)

        mock_logger.error.assert_called_once()
        assert mock_logger.error.call_args.args[1] == "error_recipe"
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
async def test_get_recipe_path_recipe_lookup_error(
    mock_autopkg_prefs: MagicMock,
) -> None:
    """Test that _get_recipe_path raises RecipeLookupError."""
    with (
        patch(
            "cloud_autopkg_runner.recipe_finder.RecipeFinder.find_recipe",
            new_callable=AsyncMock,
            side_effect=RecipeLookupError("Recipe not found"),
        ),
        pytest.raises(RecipeLookupError),
    ):
        await _get_recipe_path("test_recipe", mock_autopkg_prefs)


def test_key_value_pair() -> None:
    """Test that _key_value_pair returns the correct value."""
    cli_input = "KEY=VALUE"
    result = _key_value_pair(cli_input)

    assert result == ("KEY", "VALUE")


def test_key_value_pair_exception() -> None:
    """Test that _key_value_pair raises ArgumentTypeError on invalid input."""
    cli_input = "INVALID_KEY_VALUE"
    with pytest.raises(ArgumentTypeError):
        _key_value_pair(cli_input)


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

    assert results.reports == {"TestRecipe": mock_report}
    assert results.failures == {}
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

    assert results.reports == {}
    assert results.failures == {"BadRecipe": "Recipe could not be loaded"}
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

    assert results.reports == {}
    assert results.failures == {"TimeoutRecipe": "Timed out after 3 seconds"}
    mock_logger.error.assert_called()


@pytest.mark.asyncio
async def test_process_recipe_list_success() -> None:
    """_process_recipe_list should process items and merge worker results."""

    async def fake_worker(
        queue: asyncio.Queue, _settings: Settings, _prefs: AutoPkgPrefs
    ) -> RunResults:
        results = RunResults()
        while True:
            item = await queue.get()
            if item is STOP_WORKER:
                queue.task_done()
                break
            results.reports[item] = f"report-{item}"
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

    assert results.reports == {
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
    ) -> RunResults:
        # drain queue to avoid block
        while True:
            item = await queue.get()
            queue.task_done()
            if item is STOP_WORKER:
                break
        return RunResults()

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


@pytest.mark.asyncio
async def test_recipe_worker_survives_unexpected_error(tmp_path: Path) -> None:
    """An unexpected error must not terminate the worker mid-queue."""
    queue = asyncio.Queue()
    queue.put_nowait("Exploding")
    queue.put_nowait("Healthy")
    queue.put_nowait(STOP_WORKER)

    mock_report = MagicMock()
    healthy_recipe = MagicMock()
    healthy_recipe.name = "Healthy"
    healthy_recipe.run = AsyncMock(return_value=mock_report)

    async def create(recipe_name: str, *_args: typing.Any) -> MagicMock:
        if recipe_name == "Exploding":
            msg = "report file vanished"
            raise FileNotFoundError(msg)
        return healthy_recipe

    mock_settings = MagicMock()
    mock_settings.recipe_timeout = 10
    mock_settings.report_dir = tmp_path

    with patch("cloud_autopkg_runner.__main__._create_recipe", new=create):
        results = await _recipe_worker(queue, mock_settings, MagicMock())

    assert results.reports == {"Healthy": mock_report}
    assert "Exploding" in results.failures
    assert "FileNotFoundError" in results.failures["Exploding"]
    assert queue.empty()


@pytest.mark.asyncio
async def test_process_recipe_list_does_not_hang_when_a_worker_dies() -> None:
    """A worker that terminates early must not stall the whole run."""

    async def dying_worker(
        queue: asyncio.Queue, _settings: Settings, _prefs: AutoPkgPrefs
    ) -> RunResults:
        await queue.get()
        queue.task_done()
        msg = "worker died before consuming its sentinel"
        raise RuntimeError(msg)

    with (
        patch("cloud_autopkg_runner.__main__._recipe_worker", new=dying_worker),
        patch(
            "cloud_autopkg_runner.__main__.get_cache_plugin",
            return_value=AsyncMock().__aenter__.return_value,
        ),
        patch("cloud_autopkg_runner.settings.Settings.max_concurrency", 1),
    ):
        results = await asyncio.wait_for(
            _process_recipe_list(["A", "B"], MagicMock()), timeout=10
        )

    assert results.has_failures is True
    assert "B" in results.failures


def _report(*, failed: bool = False) -> ConsolidatedReport:
    """Build a ConsolidatedReport, optionally containing a failed item.

    Returns:
        A ConsolidatedReport suitable for exercising RunResults.
    """
    return ConsolidatedReport(
        failed_items=(
            [{"message": "boom", "recipe": "R", "traceback": "tb"}] if failed else []
        ),
        downloaded_items=[],
        pkg_built_items=[],
        munki_imported_items=[],
    )


def _cli_namespace() -> Namespace:
    """Build a Namespace with every CLI option unset.

    Returns:
        A Namespace matching the attributes _async_main reads.
    """
    return Namespace(
        autopkg_path=None,
        autopkg_pref_file=None,
        azure_account_url=None,
        cache_file=None,
        cache_plugin=None,
        cloud_container_name=None,
        config_file=None,
        key=None,
        log_file=None,
        log_format=None,
        max_concurrency=None,
        post_processor=None,
        pre_processor=None,
        recipe=None,
        recipe_list=None,
        recipe_timeout=None,
        report_dir=None,
        verbose=None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("results", "expected"),
    [
        (RunResults(reports={"A.recipe": _report()}), EXIT_SUCCESS),
        (RunResults(reports={"A.recipe": _report(failed=True)}), EXIT_FAILURE),
        (RunResults(failures={"A": "Recipe could not be loaded"}), EXIT_FAILURE),
        (RunResults(), EXIT_SUCCESS),
    ],
)
async def test_async_main_exit_code(results: RunResults, expected: int) -> None:
    """_async_main should signal recipe failures through its exit code."""
    mock_loader = MagicMock()
    mock_loader.return_value.load.return_value = {}

    with (
        patch("cloud_autopkg_runner.__main__._parse_arguments", _cli_namespace),
        patch("cloud_autopkg_runner.__main__.ConfigLoader", mock_loader),
        patch("cloud_autopkg_runner.__main__.AutoPkgPrefs", MagicMock()),
        patch("cloud_autopkg_runner.__main__.logging_config", MagicMock()),
        patch(
            "cloud_autopkg_runner.__main__._generate_recipe_list",
            return_value={"A"},
        ),
        patch(
            "cloud_autopkg_runner.__main__._process_recipe_list",
            new=AsyncMock(return_value=results),
        ),
    ):
        assert await _async_main() == expected


def test_log_run_summary_is_silent_at_error_level_on_success() -> None:
    """A successful run must not emit ERROR or WARNING output."""
    results = RunResults(reports={"A.recipe": _report(), "B.recipe": _report()})

    with patch("cloud_autopkg_runner.__main__.logger") as mock_logger:
        _log_run_summary(results)

    mock_logger.error.assert_not_called()
    mock_logger.warning.assert_not_called()
    mock_logger.info.assert_called_once()


def test_log_run_summary_reports_failures_at_error_level() -> None:
    """A failing run must state the tally at ERROR so it is always visible."""
    results = RunResults(
        reports={"A.recipe": _report(failed=True)},
        failures={"B": "Timed out after 5 seconds"},
    )

    with patch("cloud_autopkg_runner.__main__.logger") as mock_logger:
        _log_run_summary(results)

    error_messages = [call.args[0] for call in mock_logger.error.call_args_list]
    assert any("failed item(s)" in message for message in error_messages)
    assert any("Run complete" in message for message in error_messages)
    mock_logger.info.assert_not_called()


def test_log_run_summary_restates_recorded_failures_only_at_debug() -> None:
    """Failures already logged at their origin must not be repeated at ERROR."""
    results = RunResults(failures={"B": "Recipe could not be loaded"})

    with patch("cloud_autopkg_runner.__main__.logger") as mock_logger:
        _log_run_summary(results)

    mock_logger.debug.assert_called_once()
    error_messages = [call.args[0] for call in mock_logger.error.call_args_list]
    assert all("did not complete" not in message for message in error_messages)


def test_create_recipe_keeps_traceback_for_debug(
    mock_autopkg_prefs: MagicMock, tmp_path: Path
) -> None:
    """Recipe load failures log a one-line error, with the traceback at DEBUG."""

    async def run() -> None:
        with (
            patch("cloud_autopkg_runner.__main__.logger") as mock_logger,
            patch(
                "cloud_autopkg_runner.__main__._get_recipe_path",
                new=AsyncMock(side_effect=RecipeLookupError("Missing.recipe")),
            ),
        ):
            assert (
                await _create_recipe("Missing.recipe", tmp_path, mock_autopkg_prefs)
                is None
            )

        mock_logger.exception.assert_not_called()
        mock_logger.error.assert_called_once()
        assert mock_logger.debug.call_args.kwargs["exc_info"] is True

    asyncio.run(run())


def test_main_propagates_exit_code() -> None:
    """main() should terminate the process with _async_main's exit code."""
    with (
        patch("cloud_autopkg_runner.__main__.signal.signal"),
        # Patched so no un-awaited coroutine is created by main().
        patch("cloud_autopkg_runner.__main__._async_main", MagicMock()),
        patch("cloud_autopkg_runner.__main__.asyncio.run", return_value=EXIT_FAILURE),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == EXIT_FAILURE
