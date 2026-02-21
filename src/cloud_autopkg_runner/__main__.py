"""The main entry point for the cloud-autopkg-runner application.

This module orchestrates the execution of AutoPkg recipes within a cloud environment.
It handles command-line argument parsing, logging initialization, recipe discovery,
metadata management, and concurrent recipe processing.

The application workflow typically includes the following steps:
1.  Argument Parsing: Parses command-line arguments to configure its behavior.
2.  Logging Initialization: Initializes the logging system for monitoring
    and debugging based on verbosity and log file settings.
3.  Recipe List Generation: Generates a comprehensive list of AutoPkg
    recipes to be processed from various input sources.
4.  Metadata Cache Management: Initializes and interacts with a metadata
    cache plugin to optimize downloads and identify changes in recipe-managed
    software.
5.  Placeholder File Creation: Creates placeholder files in the AutoPkg
    cache to simulate existing downloads, which can be useful for testing or
    optimizing subsequent runs.
6.  Concurrent Recipe Processing: Processes the generated list of recipes
    concurrently, adhering to a configurable maximum number of concurrent tasks.
"""

import asyncio
import json
import os
import signal
import sys
from argparse import ArgumentParser, ArgumentTypeError, Namespace
from collections.abc import Iterable
from importlib.metadata import metadata
from pathlib import Path
from types import FrameType
from typing import NoReturn, TypeVar

from cloud_autopkg_runner import (
    AutoPkgPrefs,
    ConfigLoader,
    ConfigSchema,
    Recipe,
    RecipeFinder,
    Settings,
    get_cache_plugin,
    logging_config,
)
from cloud_autopkg_runner.exceptions import (
    InvalidFileContentsError,
    InvalidJsonContentsError,
    RecipeError,
)
from cloud_autopkg_runner.logging_context import recipe_context
from cloud_autopkg_runner.recipe_report import ConsolidatedReport

logger = logging_config.get_logger(__name__)

T = TypeVar("T")

# Constant that indicates a worker queue is empty and can be stopped
STOP_WORKER = "<<STOP_WORKER>>"


def _schema_overrides_from_cli(args: Namespace) -> dict[str, object]:
    """Extract configuration schema overrides from CLI arguments.

    This function translates parsed CLI arguments into a dictionary
    suitable for applying as overrides to ConfigSchema. Only arguments
    explicitly provided by the user are included.

    Args:
        args: Parsed command-line arguments.

    Returns:
        A dictionary of schema field overrides.
    """
    overrides: dict[str, object] = {}

    for key in (
        "autopkg_pref_file",
        "azure_account_url",
        "cache_file",
        "cache_plugin",
        "cloud_container_name",
        "log_file",
        "log_format",
        "max_concurrency",
        "recipe_timeout",
        "report_dir",
    ):
        if hasattr(args, key) and getattr(args, key) is not None:
            overrides[key] = getattr(args, key)

    # Handle keys that don't match
    if args.verbose is not None:
        overrides["verbosity_level"] = args.verbose
    if args.pre_processor is not None:
        overrides["pre_processors"] = args.pre_processor
    if args.post_processor is not None:
        overrides["post_processors"] = args.post_processor
    if args.key is not None:
        overrides["input_variables"] = dict(args.key)

    return overrides


def _count_iterable(iterable: Iterable[T]) -> int:
    """Count the number of elements in an iterable.

    This function consumes the entire iterable to determine its length,
    which means it should not be used on infinite iterators.

    Args:
        iterable: An iterable collection of elements of type T.

    Returns:
        The number of elements in the iterable.
    """
    return sum(1 for _element in iterable)


async def _create_recipe(
    recipe_name: str, report_dir: Path, autopkg_prefs: AutoPkgPrefs
) -> Recipe | None:
    """Create a `Recipe` object, handling potential exceptions during initialization.

    This private asynchronous helper function attempts to create a `Recipe` object
    for a given recipe name. If any errors occur during the recipe's
    initialization (e.g., the recipe file is invalid or cannot be found due to
    `InvalidFileContentsError` or `RecipeError`), the error is caught,
    logged, and the function returns `None`. This allows the application to
    continue processing other recipes even if some are malformed or missing.

    Args:
        recipe_name: The name of the recipe to create.
        report_dir: A `Path` object containing the directory to store recipe run
            reports.
        autopkg_prefs: An `AutoPkgPrefs` object containing AutoPkg's preferences,
            used to initialize the `Recipe` object.

    Returns:
        A `Recipe` object if the creation was successful, otherwise `None`.
    """
    try:
        recipe_path = await _get_recipe_path(recipe_name, autopkg_prefs)
        return Recipe(recipe_path, report_dir, autopkg_prefs)
    except (InvalidFileContentsError, RecipeError):
        logger.exception("Failed to create `Recipe` object: %s", recipe_name)
        return None


def _generate_recipe_list(schema: ConfigSchema, args: Namespace) -> set[str]:
    """Generate a comprehensive list of recipe names from various input sources.

    This function reconciles recipe lists from CLI arguments, the configuration
    file, and environment variables. The order of precedence is:

    1.  CLI arguments (`--recipe-list` and/or `--recipe`): If present, these
        sources are used exclusively. Configuration file recipes are ignored.
    2.  Configuration file (`schema.recipes`): Used only if no CLI recipe
        arguments are provided.
    3.  Environment variable (`RECIPE`): This is always added to the final
        list, regardless of the primary source.

    Args:
        schema: A `ConfigSchema` object containing configuration loaded from a file.
        args: A `Namespace` object containing parsed command-line arguments.

    Returns:
        A `set` of strings, where each string is a unique recipe name to be processed.

    Raises:
        InvalidJsonContentsError: If the JSON file specified by `args.recipe_list`
            contains invalid JSON, indicating a malformed input file.
    """
    logger.debug("Generating recipe list...")
    output: set[str] = set()

    if args.recipe_list or args.recipe:
        if args.recipe_list:
            try:
                output.update(json.loads(Path(args.recipe_list).read_text("utf-8")))
            except json.JSONDecodeError as exc:
                raise InvalidJsonContentsError(args.recipe_list) from exc
        if args.recipe:
            output.update(args.recipe)
    elif schema.recipes:
        output.update(schema.recipes)

    if env_recipe := os.getenv("RECIPE", ""):
        output.add(env_recipe)

    logger.debug("Recipe list generated: %s", output)
    return output


async def _get_recipe_path(recipe_name: str, autopkg_prefs: AutoPkgPrefs) -> Path:
    """Helper function to asynchronously find a recipe path.

    This private asynchronous helper function utilizes the `RecipeFinder` class
    to locate the `Path` to a specific AutoPkg recipe file. It acts as a wrapper
    around the `RecipeFinder`'s functionality, simplifying recipe path resolution.

    Args:
        recipe_name: The name of the recipe to find the path for.
        autopkg_prefs: An `AutoPkgPrefs` object containing AutoPkg's preferences,
            used to initialize the `RecipeFinder`.

    Returns:
        The `Path` object to the located recipe file.
    """
    finder = RecipeFinder(autopkg_prefs)
    return await finder.find_recipe(recipe_name)


def _key_value_pair(string: str) -> tuple[str, str]:
    """Parse a string in the format 'KEY=VALUE' into a tuple.

    This helper function is designed to be used as a type for argparse arguments that
    expect key-value pairs. It takes a string input, splits it on the first
    '=' character, and returns a tuple containing the key and value.

    Args:
        string: A string in the format 'KEY=VALUE'.

    Returns:
        A tuple containing a key-value pair

    Raises:
        ArgumentTypeError: If the input string does not contain an '=',
            the key is empty, or the value is empty
    """
    key, sep, value = string.partition("=")
    if not sep or not key or not value:
        raise ArgumentTypeError(  # noqa: TRY003
            f"Invalid input '{string}'. Expected format: KEY=VALUE"
        )
    return key, value


def _parse_arguments() -> Namespace:
    """Parse command-line arguments using argparse.

    This private helper function defines the expected command-line arguments
    for the application using `argparse`. It configures various options such
    as verbosity level, recipe sources (individual or list), log file location,
    pre/post-processors, report directory, maximum concurrency for tasks,
    cache plugin details, and AutoPkg-specific preferences. The parsed arguments
    are then returned as a `Namespace` object for easy access throughout the
    application.

    Returns:
        A `Namespace` object containing the parsed command-line arguments.
    """
    project_metadata = metadata("cloud-autopkg-runner")

    parser = ArgumentParser(
        prog=project_metadata["Name"],
        description=project_metadata["Summary"],
    )

    # Standard Flags
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {project_metadata['Version']}",
    )

    # General / Logging
    general = parser.add_argument_group("General Options")
    general.add_argument(
        "-v",
        "--verbose",
        action="count",
        help="Verbosity level. Can be specified multiple times. (-vvv)",
    )
    general.add_argument(
        "--config-file",
        help="Path to a Cloud AutoPkg Runner config file.",
        type=Path,
    )
    general.add_argument(
        "--log-file",
        help="Path to the log file. If not specified, no file logging will occur.",
        type=Path,
    )
    general.add_argument(
        "--log-format",
        help="Sets the log file format. Requires `--log-file` be configured.",
        choices=["text", "json"],
        type=str,
    )
    general.add_argument(
        "--report-dir",
        help="Path to the directory used for storing AutoPkg recipe reports.",
        type=Path,
    )
    general.add_argument(
        "--max-concurrency",
        help="Limit the number of concurrent tasks.",
        type=int,
    )
    general.add_argument(
        "--recipe-timeout",
        help="Timeout in seconds for each recipe task. Defaults to 300 (5 minutes).",
        type=int,
    )

    # Recipe Selection
    recipes = parser.add_argument_group("Recipe Selection")
    recipes.add_argument(
        "-r",
        "--recipe",
        action="append",
        help="A recipe name. Can be specified multiple times.",
    )
    recipes.add_argument(
        "--recipe-list",
        help="Path to a list of recipe names in JSON format.",
        type=Path,
    )
    recipes.add_argument(
        "-k",
        "--key",
        metavar="KEY=VALUE",
        action="append",
        help=(
            "Specify inputs to use in the recipe. "
            "These inputs will take precedence and override recipe inputs. "
            "Can be specified multiple times."
        ),
        type=_key_value_pair,
    )

    # Processors
    processors = parser.add_argument_group("Pre/Post Processors")
    processors.add_argument(
        "--pre-processor",
        action="append",
        help=(
            "Specify a pre-processor to run before the main AutoPkg recipe. "
            "Can be specified multiple times."
        ),
        type=str,
    )
    processors.add_argument(
        "--post-processor",
        action="append",
        help=(
            "Specify a post-processor to run after the main AutoPkg recipe. "
            "Can be specified multiple times."
        ),
        type=str,
    )

    # Cache Options
    cache = parser.add_argument_group("Cache Options")
    cache.add_argument(
        "--cache-plugin",
        # Use the entry point names
        choices=["azure", "gcs", "json", "s3", "sqlite"],
        help="The cache plugin to use.",
        type=str,
    )
    cache.add_argument(
        "--cache-file",
        help="Path to the file that stores the download metadata cache.",
        type=str,
    )
    cache.add_argument(
        "--cloud-container-name",
        help="Bucket/Container name for cloud plugins (azure, gcs, s3).",
        type=str,
    )
    cache.add_argument(
        "--azure-account-url",
        help="Azure account URL",
        type=str,
    )

    # AutoPkg
    autopkg = parser.add_argument_group("AutoPkg Preferences")
    autopkg.add_argument(
        "--autopkg-pref-file",
        help="Path to the AutoPkg preferences file.",
        type=Path,
    )

    return parser.parse_args()


async def _process_recipe_list(
    recipe_list: Iterable[str], autopkg_prefs: AutoPkgPrefs
) -> dict[str, ConsolidatedReport]:
    """Create and run AutoPkg recipes using a worker queue pattern.

    This orchestrates execution by populating a work queue with recipe names
    and spawning a fixed number of worker tasks. This prevents "thundering herd"
    issues during recipe object creation and allows for cleaner timeout handling.

    Args:
        recipe_list: An iterable of recipe names.
        autopkg_prefs: AutoPkg preferences.

    Returns:
        A dictionary of recipe names mapped to their reports.
    """
    settings = Settings()

    num_workers = min(settings.max_concurrency, _count_iterable(recipe_list))

    # Populate the Queue
    queue: asyncio.Queue[str] = asyncio.Queue()
    for recipe_name in recipe_list:
        queue.put_nowait(recipe_name)

    for _ in range(num_workers):
        queue.put_nowait(STOP_WORKER)

    logger.info(
        "Processing %d recipes with %d workers...",
        queue.qsize() - num_workers,
        num_workers,
    )

    # Process the queue
    async with get_cache_plugin():
        workers = [
            asyncio.create_task(_recipe_worker(queue, settings, autopkg_prefs))
            for _ in range(num_workers)
        ]
        await queue.join()
        worker_results = await asyncio.gather(*workers)

    final_results: dict[str, ConsolidatedReport] = {}
    for result_chunk in worker_results:
        final_results.update(result_chunk)

    return final_results


async def _recipe_worker(
    queue: asyncio.Queue[str], settings: Settings, autopkg_prefs: AutoPkgPrefs
) -> dict[str, ConsolidatedReport]:
    """Consume recipe names from the shared work queue and execute them to completion.

    Each worker processes items until it encounters the `STOP_WORKER` sentinel. For
    every recipe name retrieved from the queue, the worker performs the full
    execution lifecycle:

    1.  Set the per-task logging context (`recipe_context`) so all log output is
        tagged with the active recipe name.
    2.  Resolve the recipe path and construct a `Recipe` instance. Invalid or
        unreadable recipes are logged and skipped without terminating the worker.
    3.  Execute the recipe with a timeout using `asyncio.wait_for()`, capturing the
        resulting `ConsolidatedReport` on success.
    4.  Handle and log timeouts and unexpected exceptions without interrupting
        other workers.
    5.  Reset the logging context and mark the queue item as processed.

    The worker returns a mapping of recipe names to their final `ConsolidatedReport`
    objects. Multiple workers may run concurrently; their partial result maps are
    merged by the caller.

    Args:
        queue: A work queue containing recipe names followed by sentinel values
            equal to `STOP_WORKER` for each worker.
        settings: Application settings controlling concurrency, timeouts, reporting
            directories, and other runtime options.
        autopkg_prefs: The AutoPkg preference set used for recipe discovery and
            execution.

    Returns:
        A dictionary mapping recipe names to their corresponding
        `ConsolidatedReport` instances.

    Raises:
        Exception: Any unexpected error inside the worker is logged and re-raised
            to allow the caller to fail fast, while still ensuring proper cleanup.
    """
    results: dict[str, ConsolidatedReport] = {}

    while True:
        recipe_name = await queue.get()
        if recipe_name is STOP_WORKER:
            queue.task_done()
            break

        token = recipe_context.set(
            recipe_name.removesuffix(".yaml").removesuffix(".recipe")
        )
        try:
            logger.info("Starting recipe %s", recipe_name)

            recipe = await _create_recipe(
                recipe_name, settings.report_dir, autopkg_prefs
            )
            if not recipe:
                continue

            logger.debug("Executing recipe %s", recipe_name)

            try:
                report = await asyncio.wait_for(
                    recipe.run(), timeout=settings.recipe_timeout
                )
                results[recipe.name] = report
            except (asyncio.TimeoutError, TimeoutError):
                logger.error(  # noqa: TRY400
                    "Recipe %s timed out after %s seconds",
                    recipe_name,
                    settings.recipe_timeout,
                )

        except Exception:
            logger.exception("Worker failed unexpectedly on recipe '%s'", recipe_name)
            raise
        finally:
            queue.task_done()
            recipe_context.reset(token)

    return results


def _signal_handler(sig: int, _frame: FrameType | None) -> NoReturn:
    """Handle signals for graceful application shutdown.

    This private helper function is registered as a signal handler to catch
    system signals such as `SIGINT` (typically generated by Ctrl+C) and `SIGTERM`
    (often sent by the `kill` command). When such a signal is received, this
    handler logs an error message indicating the signal and then gracefully
    exits the application with an exit code of 0.

    Args:
        sig: The signal number (an integer, e.g., `signal.SIGINT`).
        _frame: The current stack frame object, which is typically unused in
            simple signal handlers and thus ignored.
    """
    logger.error("Signal %s received. Exiting...", sig)
    sys.exit(0)


async def _async_main() -> None:
    """Asynchronous main function to orchestrate the application's workflow.

    This private asynchronous function serves as the central orchestration point
    for the cloud-autopkg-runner application. It performs the following key steps:
    1.  Parse Arguments: Calls `_parse_arguments()` to interpret command-line inputs.
    2.  Apply Settings: Calls `_apply_args_to_settings()` to configure global
        application settings based on the parsed arguments.
    3.  Initialize Logging: Initializes the application's logging system using
        `logging_config.initialize_logger()`.
    4.  Load AutoPkg Preferences: Loads AutoPkg's global preferences using
        `AutoPkgPrefs()`.
    5.  Generate Recipe List: Calls `_generate_recipe_list()` to compile a definitive
        list of recipes to be processed.
    6.  Process Recipes: Calls `_process_recipe_list()` to asynchronously execute all
        identified recipes, managing concurrency and reporting.

    This function coordinates the overall flow of the application from start to
    recipe processing completion.
    """
    args = _parse_arguments()
    cli_overrides = _schema_overrides_from_cli(args)

    config_data = ConfigLoader(args.config_file).load()
    schema = ConfigSchema.from_dict(config_data).with_overrides(cli_overrides)

    settings = Settings()
    settings.load(schema)

    logging_config.initialize_logger(
        settings.verbosity_level, settings.log_file, settings.log_format
    )

    autopkg_prefs = AutoPkgPrefs(settings.autopkg_pref_file)

    recipe_list = _generate_recipe_list(schema, args)
    _results = await _process_recipe_list(recipe_list, autopkg_prefs)


def main() -> None:
    """Synchronous entry point for the application.

    This function serves as the primary synchronous entry point for the
    cloud-autopkg-runner application. It is designed to be called by setuptools
    or directly when the script is executed. It performs two main tasks:
    1.  Signal Handling: Sets up `_signal_handler` to gracefully manage
        `SIGINT` (Ctrl+C) and `SIGTERM` signals, ensuring the application exits
        cleanly.
    2.  Asynchronous Execution: Initializes a new `asyncio` event loop and
        runs the `_async_main()` asynchronous function within it, thereby
        starting the core application logic.
    """
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
