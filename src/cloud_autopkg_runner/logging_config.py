"""Module for initializing and managing logging within cloud-autopkg-runner.

This module provides functions for configuring the logging system,
allowing for flexible control over the verbosity level and output
destinations (console and/or file). It also offers a convenient way to
retrieve logger instances for use in other modules.

The logging system is enhanced with recipe-level contextual information.
When the caller sets the context variable in cloud_autopkg_runner.logging_context,
every log line automatically includes the recipe name, even when running concurrently.
"""

import json
import logging
import sys
import time
from typing import Any, ClassVar, TextIO

from cloud_autopkg_runner.logging_context import recipe_context


class ColorFormatter(logging.Formatter):
    """Add ANSI coloring to log level names while preserving padding."""

    COLORS: ClassVar[dict[str, str]] = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[41m",  # Red background
    }
    RESET: ClassVar[str] = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        """Render log message with colorized level names."""
        # Let the base class format the record first
        msg = super().format(record)

        color = self.COLORS.get(record.levelname)
        if not color:
            return msg

        # Replace the exact (already padded) level text inside msg
        padded = f"{record.levelname:<7}"
        colored = f"{color}{padded}{self.RESET}"

        return msg.replace(padded, colored, 1)


class UtcFormatter(logging.Formatter):
    """Formatter that forces timestamps to be rendered in UTC."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the formatter and enforce use of UTC timestamps."""
        super().__init__(*args, **kwargs)
        self.converter = time.gmtime  # Ensures UTC timestamps


class JsonFormatter(UtcFormatter):
    """Structured JSON formatter for SIEM-friendly log files.

    This formatter serializes log records into a single-line JSON object.
    It includes timestamp, level, contextual recipe information, module
    metadata, and message content. The timestamp is always emitted in
    UTC using an ISO-8601/RFC3339-compatible format (e.g.,
    "2025-11-17T02:05:23Z").

    Args:
        datefmt: Optional format string used for timestamp rendering.
            Defaults to "%Y-%m-%dT%H:%M:%SZ" (UTC ISO-8601).

    Returns:
        A JSON string representing the structured log record.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Serialize the log record into a JSON-formatted string.

        Args:
            record: The log record to format.

        Returns:
            A JSON string containing structured log fields.
        """
        log_entry: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "context": str(getattr(record, "recipe", __package__)),
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info:
            log_entry["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, separators=(",", ":"), sort_keys=True)


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


def initialize_logger(
    verbosity_level: int, log_file: str | None = None, log_format: str = "text"
) -> None:
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
        log_format: Optional format for the log file.
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
    console_formatter = ColorFormatter("%(levelname)-7s %(recipe)-30s %(message)s")
    console_handler.setFormatter(console_formatter)
    console_handler.addFilter(context_filter)
    logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        timestamp_format = "%Y-%m-%dT%H:%M:%SZ"
        file_handler: logging.FileHandler = logging.FileHandler(log_file, mode="w")
        file_handler.setLevel(logging.DEBUG)
        if log_format == "json":
            file_formatter = JsonFormatter(datefmt=timestamp_format)
        else:
            file_formatter = UtcFormatter(
                "%(asctime)s %(levelname)-7s %(recipe)-30s %(message)s",
                datefmt=timestamp_format,
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
