"""The main entry point for the cloud-autopkg-runner application.

This module orchestrates the execution of AutoPkg recipes within a cloud environment.
It handles command-line argument parsing, logging initialization, recipe discovery,
metadata management, and concurrent recipe processing.

The application:
1.  Parses command-line arguments to configure its behavior.
2.  Initializes the logging system for monitoring and debugging.
3.  Generates a list of AutoPkg recipes to be processed.
4.  Loads a metadata cache to optimize downloads and identify changes.
5.  Creates dummy files to simulate existing downloads for testing or efficiency.
6.  Processes the list of recipes concurrently, managing a maximum number of
    concurrent tasks.
"""

import asyncio
import json
import os
import signal
import sys
from argparse import ArgumentParser, Namespace
from collections.abc import Iterable
from pathlib import Path
from types import FrameType
from typing import NoReturn

from cloud_autopkg_runner import (
    Settings,
    file_utils,
    logging_config,
    metadata_cache,
    recipe,
    recipe_finder,
)
from cloud_autopkg_runner.exceptions import (
    InvalidFileContents,
    InvalidJsonContents,
    RecipeException,
)
from cloud_autopkg_runner.recipe_report import ConsolidatedReport


def _apply_args_to_settings(args: Namespace) -> None:
    """Apply command-line arguments to configure application settings.

    This function takes a Namespace object containing parsed command-line arguments
    and applies their values to the corresponding settings in the `settings` module.
    This allows the application to be configured dynamically based on user input.

    Args:
        args: A Namespace object containing parsed command-line arguments.
    """
    settings = Settings()

    settings.log_file = args.log_file
    settings.max_concurrency = args.max_concurrency
    settings.report_dir = args.report_dir
    settings.verbosity_level = args.verbose

    settings.cache_plugin = args.cache_plugin
    settings.cache_file = args.cache_file

    # Plugin-specific arguments
    if settings.cache_plugin == "azure":
        settings.azure_account_url = args.azure_account_url

    if settings.cache_plugin in {"azure", "gcs", "s3"}:
        settings.cloud_container_name = args.cloud_container_name


async def _create_recipe(recipe_name: str) -> recipe.Recipe | None:
    """Create a Recipe object, handling potential exceptions during initialization.

    This function attempts to create a `Recipe` object for a given recipe name.
    If any exceptions occur during the recipe's initialization (e.g., the recipe
    file is invalid or cannot be found), the exception is caught, logged, and
    the function returns None.

    Args:
        recipe_name: The name of the recipe to create.

    Returns:
        A Recipe object if the creation was successful, otherwise None.
    """
    try:
        settings = Settings()
        recipe_path = await _get_recipe_path(recipe_name)
        return recipe.Recipe(recipe_path, settings.report_dir)
    except (InvalidFileContents, RecipeException):
        logger = logging_config.get_logger(__name__)
        logger.exception("Failed to create recipe: %s", recipe_name)
        return None


def _generate_recipe_list(args: Namespace) -> set[str]:
    """Generate a comprehensive list of recipe names from various input sources.

    This function combines recipe names from the following sources:
    - A JSON file specified via the '--recipe-list' command-line argument.
    - Individual recipe names provided via the '--recipe' command-line argument.
    - The 'RECIPE' environment variable.

    The function ensures that the final list contains only unique recipe names.

    Args:
        args: A Namespace object containing parsed command-line arguments.

    Returns:
        A set of strings, where each string is a unique recipe name.

    Raises:
        InvalidJsonContents: If the JSON file specified by 'args.recipe_list'
            contains invalid JSON.
    """
    logger = logging_config.get_logger(__name__)
    logger.debug("Generating recipe list...")

    output: set[str] = set()

    if args.recipe_list:
        try:
            output.update(json.loads(Path(args.recipe_list).read_text("utf-8")))
        except json.JSONDecodeError as exc:
            raise InvalidJsonContents(args.recipe_list) from exc

    if args.recipe:
        output.update(args.recipe)

    if os.getenv("RECIPE"):
        output.add(os.getenv("RECIPE", ""))

    logger.debug("Recipe list generated: %s", output)
    return output


async def _get_recipe_path(recipe_name: str) -> Path:
    """Helper function to asynchronously find a recipe path.

    Args:
        recipe_name: The name of the recipe to find the path for.

    Returns:
        The Path to a given recipe.
    """
    finder = recipe_finder.RecipeFinder()
    return await finder.find_recipe(recipe_name)


def _parse_arguments() -> Namespace:
    """Parse command-line arguments using argparse.

    This function defines the expected command-line arguments and converts them
    into a Namespace object for easy access. These arguments control the
    application's behavior, such as verbosity level, recipe sources, cache and
    log file locations, pre/post-processors, report directory, and maximum
    concurrency.

    Returns:
        A Namespace object containing the parsed command-line arguments.
    """
    parser = ArgumentParser()
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Verbosity level. Can be specified multiple times. (-vvv)",
    )
    parser.add_argument(
        "-r",
        "--recipe",
        action="append",
        help="A recipe name. Can be specified multiple times.",
    )
    parser.add_argument(
        "--recipe-list",
        help="Path to a list of recipe names in JSON format.",
        type=Path,
    )
    parser.add_argument(
        "--log-file",
        help="Path to the log file. If not specified, no file logging will occur.",
        type=Path,
    )
    parser.add_argument(
        "--post-processor",
        action="append",
        help=(
            "Specify a post-processor to run after the main AutoPkg recipe."
            "Can be specified multiple times."
        ),
        type=str,
    )
    parser.add_argument(
        "--pre-processor",
        action="append",
        help=(
            "Specify a pre-processor to run before the main AutoPkg recipe. "
            "Can be specified multiple times."
        ),
        type=str,
    )
    parser.add_argument(
        "--report-dir",
        help="Path to the directory used for storing AutoPkg recipe reports.",
        default="",
        type=Path,
    )
    parser.add_argument(
        "--max-concurrency",
        help="Limit the number of concurrent tasks.",
        default=10,
        type=int,
    )

    # Plugin-specific arguments

    parser.add_argument(
        "--cache-plugin",
        # Use the entry point names
        choices=["azure", "gcs", "json", "s3", "sqlite"],
        help="The cache plugin to use (azure, gcs, json, s3, and sqlite).",
        type=str,
    )
    parser.add_argument(
        "--cache-file",
        default="metadata_cache.json",
        help="Path to the file that stores the download metadata cache.",
        type=str,
    )
    parser.add_argument(
        "--azure-account-url",
        help="Azure account URL",
        type=str,
    )
    parser.add_argument(
        "--cloud-container-name",
        help="Bucket/Container name",
        type=str,
    )

    return parser.parse_args()


async def _process_recipe_list(
    recipe_list: Iterable[str],
) -> dict[str, ConsolidatedReport]:
    """Create and run AutoPkg recipes concurrently.

    This function takes a list of recipe names, creates `Recipe` objects for each
    name, and then runs these recipes concurrently using `asyncio.gather`. It
    manages a maximum number of concurrent tasks using a semaphore.

    Args:
        recipe_list: An iterable of recipe names (strings).

    Returns:
        A dictionary where the keys are recipe names and the values are
        ConsolidatedReport objects representing the results of running each recipe.
    """
    logger = logging_config.get_logger(__name__)
    logger.debug("Processing recipes...")

    await file_utils.create_dummy_files(recipe_list)

    # Create Recipe objects concurrently
    recipes: list[recipe.Recipe] = [
        recipe
        for recipe in await asyncio.gather(
            *[_create_recipe(recipe_name) for recipe_name in recipe_list]
        )
        if recipe is not None
    ]

    # Run recipes concurrently
    results = await asyncio.gather(*[_run_recipe(recipe) for recipe in recipes])

    await metadata_cache.get_cache_plugin().save()

    return dict(results)


async def _run_recipe(
    recipe: recipe.Recipe,
) -> tuple[str, ConsolidatedReport]:
    """Run a single AutoPkg recipe with a concurrency limit.

    This function runs a single AutoPkg recipe, limiting the number of concurrent
    tasks using an asyncio.Semaphore. It returns the recipe name and the
    ConsolidatedReport object containing the results of the recipe run.

    Args:
        recipe: The Recipe object to run.

    Returns:
        A tuple containing the recipe name and the ConsolidatedReport object.
    """
    logger = logging_config.get_logger(__name__)
    settings = Settings()
    async with asyncio.Semaphore(settings.max_concurrency):
        logger.debug("Running recipe %s", recipe.name)
        return recipe.name, await recipe.run()


def _signal_handler(sig: int, _frame: FrameType | None) -> NoReturn:
    """Handle signals for graceful application shutdown.

    This function is registered as a signal handler to catch signals such as
    SIGINT (Ctrl+C) and SIGTERM (the `kill` command). When a signal is received,
    this handler logs an error message and then exits the application.

    Args:
        sig: The signal number (an integer).
        _frame: The frame object (unused).
    """
    logger = logging_config.get_logger(__name__)
    logger.error("Signal %s received. Exiting...", sig)
    sys.exit(0)


async def _async_main() -> None:
    """Asynchronous main function to orchestrate the application's workflow.

    This function orchestrates the core logic of the application, including:
    - Parsing command-line arguments.
    - Initializing logging.
    - Generating a list of recipes to process.
    - Creating dummy files to simulate previous downloads.
    - Processing the recipe list concurrently.
    """
    args = _parse_arguments()
    _apply_args_to_settings(args)

    logging_config.initialize_logger(args.verbose, args.log_file)

    recipe_list = _generate_recipe_list(args)
    _results = await _process_recipe_list(recipe_list)


def main() -> None:
    """Synchronous entry point for the application.

    This function serves as a bridge between the synchronous environment
    expected by setuptools and the asynchronous `_async_main` function. It
    sets up signal handlers for graceful shutdown and then uses `asyncio.run()`
    to execute the asynchronous main function within a new event loop.
    """
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
