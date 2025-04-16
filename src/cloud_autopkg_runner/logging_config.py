"""Module for initializing and managing logging within cloud-autopkg-runner.

This module provides functions for configuring the logging system,
allowing for flexible control over the verbosity level and output
destinations (console and/or file). It also offers a convenient way to
retrieve logger instances for use in other modules.

Functions:
    initialize_logger: Initializes the logging system with a console handler
        and an optional file handler.
    get_logger: Retrieves a logger instance with the specified name.
"""

import logging
import sys
from typing import TextIO


def initialize_logger(verbosity_level: int, log_file: str | None = None) -> None:
    """Initializes the logging system.

    Configures the root logger with a console handler and an optional file
    handler. The console handler's log level is determined by the
    `verbosity_level` argument, while the file handler (if enabled) logs at
    the DEBUG level.

    Args:
        verbosity_level: An integer representing the verbosity level.  Maps to
            logging levels as follows:
            0: ERROR, 1: WARNING, 2: INFO, 3: DEBUG (and higher).
        log_file: Optional path to a log file. If specified, logging output
            will be written to this file in addition to the console. If None,
            no file logging will occur.
    """
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    logger.handlers.clear()

    log_levels: list[int] = [
        logging.ERROR,
        logging.WARNING,
        logging.INFO,
        logging.DEBUG,
    ]
    level: int = log_levels[min(verbosity_level, len(log_levels) - 1)]

    # Console handler
    console_handler: logging.StreamHandler[TextIO] = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_formatter: logging.Formatter = logging.Formatter(
        "%(module)-20s %(levelname)-8s %(message)s"
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        file_handler: logging.FileHandler = logging.FileHandler(log_file, mode="w")
        file_handler.setLevel(logging.DEBUG)
        file_formatter: logging.Formatter = logging.Formatter(
            "%(asctime)s %(module)-20s %(levelname)-8s %(message)s",
            datefmt="%m-%d %H:%M",
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance.

    Retrieves a logger instance with the specified name. This function
    simplifies the process of obtaining loggers for use in different
    modules of the application.

    Args:
        name: The name of the logger to retrieve (typically `__name__`).

    Returns:
        A Logger instance with the specified name.
    """
    return logging.getLogger(name)
