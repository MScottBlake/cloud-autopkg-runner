"""Module for initializing and managing logging within cloud-autopkg-runner.

This module provides functions for configuring the logging system,
allowing for flexible control over the verbosity level and output
destinations (console and/or file). It also offers a convenient way to
retrieve logger instances for use in other modules.

The logging system is enhanced with recipe-level contextual information.
When the caller sets the context variable in cloud_autopkg_runner.logging_context,
every log line automatically includes the recipe name, even when running concurrently.
"""

import logging
import sys
from typing import TextIO

from cloud_autopkg_runner.logging_context import recipe_context


class RecipeContextFilter(logging.Filter):
    """Inject contextual recipe information into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Add the current recipe context to the log record.

        This method is called for each log record emitted. It sets
        `record.recipe` to the value stored in the recipe_context
        ContextVar, or "-" if the context variable is not set.

        Returns:
            True always, so that the record is not filtered out.
        """
        try:
            record.recipe = recipe_context.get()
        except LookupError:
            record.recipe = __package__

        return True


def initialize_logger(verbosity_level: int, log_file: str | None = None) -> None:
    """Initializes the logging system.

    Configures the root logger with a console handler and an optional file
    handler. The console handler's log level is determined by the
    `verbosity_level` argument, while the file handler (if enabled) logs at
    the DEBUG level.

    A logging Filter is added that inserts the current recipe context
    (if set) into each log record as `%(recipe)s`.

    Args:
        verbosity_level: An integer representing the verbosity level.  Maps to
            logging levels as follows:
            0: ERROR, 1: WARNING, 2: INFO, 3: DEBUG (and higher).
        log_file: Optional path to a log file. If specified, logging output
            will be written to this file in addition to the console. If None,
            no file logging will occur.
    """
    logger = logging.getLogger(__name__.split(".")[0])
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    # Map verbosity flags to log levels
    log_levels: list[int] = [
        logging.ERROR,
        logging.WARNING,
        logging.INFO,
        logging.DEBUG,
    ]
    level: int = log_levels[min(verbosity_level, len(log_levels) - 1)]

    # Attach recipe context filter
    context_filter = RecipeContextFilter()
    logger.addFilter(context_filter)

    # Console handler
    console_handler: logging.StreamHandler[TextIO] = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_formatter = logging.Formatter("%(levelname)-7s %(recipe)-25s %(message)s")
    console_handler.setFormatter(console_formatter)
    console_handler.addFilter(context_filter)
    logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        file_handler: logging.FileHandler = logging.FileHandler(log_file, mode="w")
        file_handler.setLevel(logging.DEBUG)
        file_formatter: logging.Formatter = logging.Formatter(
            "%(asctime)s %(levelname)-7s %(recipe)-25s %(message)s",
            datefmt="%m-%d %H:%M",
        )
        file_handler.setFormatter(file_formatter)
        file_handler.addFilter(context_filter)
        logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance.

    Retrieves a logger instance with the specified name. This function
    simplifies the process of obtaining loggers for use in different
    modules of the application.

    This wrapper allows for future enhancements, such as adding context
    filters or structured logging.

    This does not configure handlers or log levels; it simply returns
    the logger with the given name. Use `initialize_logger()` at
    application startup to configure logging output.

    Args:
        name: The name of the logger to retrieve (typically `__name__`).

    Returns:
        A Logger instance with the specified name.
    """
    return logging.getLogger(name)
