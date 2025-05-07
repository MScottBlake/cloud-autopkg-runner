import logging
from pathlib import Path

import pytest

from cloud_autopkg_runner import logging_config


@pytest.mark.parametrize(
    ("verbosity_level", "expected_level"),
    [
        (0, logging.ERROR),  # Level should be ERROR
        (1, logging.WARNING),  # Level should be WARNING
        (2, logging.INFO),  # Level should be INFO
        (3, logging.DEBUG),  # Level should be DEBUG
    ],
)
def test_console_handler_levels(verbosity_level: int, expected_level: int) -> None:
    """Test that verbosity levels are set correctly."""
    logging_config.initialize_logger(verbosity_level=verbosity_level, log_file=None)
    logger = logging.getLogger()

    # Get the most recent StreamHandler (console handler)
    console_handler = next(
        (h for h in logger.handlers if isinstance(h, logging.StreamHandler)), None
    )

    assert console_handler is not None
    assert console_handler.level == expected_level


def test_logs_to_console_but_not_file(tmp_path: Path) -> None:
    """Test logging without a log file."""
    log_file = tmp_path / "test.log"
    if log_file.exists():
        log_file.unlink()

    # Initialize logger with no file output
    logging_config.initialize_logger(verbosity_level=1, log_file=None)
    logger = logging.getLogger()

    # Assert no file handler was added (log file should not exist)
    file_handler = next(
        (h for h in logger.handlers if isinstance(h, logging.FileHandler)), None
    )
    assert file_handler is None  # No file handler should be added

    # Assert that the log file was not created
    assert not log_file.exists()


def test_logs_to_file(tmp_path: Path) -> None:
    """Test that log messages are written to the specified file."""
    log_file = tmp_path / "test.log"

    logging_config.initialize_logger(verbosity_level=1, log_file=str(log_file))
    logger = logging.getLogger()

    logger.info("This should go to both console and file")

    file_handler = next(
        (h for h in logger.handlers if isinstance(h, logging.FileHandler)), None
    )
    assert file_handler is not None

    assert log_file.exists()

    # Check if the message is in the file
    contents = log_file.read_text()
    assert "This should go to both console and file" in contents
