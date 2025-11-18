import json
import logging
from pathlib import Path

import pytest

from cloud_autopkg_runner import logging_config
from cloud_autopkg_runner.logging_config import (
    ColorFormatter,
    JsonFormatter,
    UtcFormatter,
)


def _get_handler(logger: logging.Logger, cls: type) -> logging.Handler | None:
    return next((h for h in logger.handlers if isinstance(h, cls)), None)


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
    logger = logging.getLogger("cloud_autopkg_runner")

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
    logger = logging.getLogger("cloud_autopkg_runner")

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
    logger = logging.getLogger("cloud_autopkg_runner")

    logger.info("This should go to both console and file")

    file_handler = next(
        (h for h in logger.handlers if isinstance(h, logging.FileHandler)), None
    )
    assert file_handler is not None

    assert log_file.exists()

    # Check if the message is in the file
    contents = log_file.read_text()
    assert "This should go to both console and file" in contents


def test_log_format_text_creates_utc_formatter(tmp_path: Path) -> None:
    """Verify that text log format uses UtcFormatter for file output."""
    log_file = tmp_path / "text.log"

    logging_config.initialize_logger(
        verbosity_level=2,
        log_file=str(log_file),
        log_format="text",
    )

    logger = logging.getLogger("cloud_autopkg_runner")

    file_handler = _get_handler(logger, logging.FileHandler)
    assert file_handler is not None
    assert isinstance(file_handler.formatter, UtcFormatter)

    logger.info("hello text format")

    logs = log_file.read_text()
    assert "hello text format" in logs
    assert "Z" in logs  # ensure UTC timestamps


def test_log_format_json_uses_json_formatter(tmp_path: Path) -> None:
    """Verify that json log format uses JsonFormatter for file output."""
    log_file = tmp_path / "json.log"

    logging_config.initialize_logger(
        verbosity_level=2,
        log_file=str(log_file),
        log_format="json",
    )

    logger = logging.getLogger("cloud_autopkg_runner")

    file_handler = _get_handler(logger, logging.FileHandler)
    assert file_handler is not None
    assert isinstance(file_handler.formatter, JsonFormatter)

    logger.error("json test message")

    contents = log_file.read_text().strip()
    assert contents.startswith("{")
    assert contents.endswith("}")


def test_json_log_file_contains_valid_json(tmp_path: Path) -> None:
    """Ensure that JSON log output is valid and parseable."""
    log_file = tmp_path / "valid.json"

    logging_config.initialize_logger(
        verbosity_level=3,
        log_file=str(log_file),
        log_format="json",
    )

    logger = logging.getLogger("cloud_autopkg_runner")
    logger.warning("parseable JSON")

    raw = log_file.read_text().strip()
    parsed = json.loads(raw)

    assert isinstance(parsed, dict)
    assert parsed["message"] == "parseable JSON"
    assert parsed["level"] == "WARNING"
    assert "timestamp" in parsed
    assert parsed["timestamp"].endswith("Z")


def test_json_log_includes_expected_fields(tmp_path: Path) -> None:
    """Ensure all StructuredLogEntry fields are present in json mode."""
    log_file = tmp_path / "fields.json"

    logging_config.initialize_logger(
        verbosity_level=3,
        log_file=str(log_file),
        log_format="json",
    )

    logger = logging.getLogger("cloud_autopkg_runner")
    logger.info("field test")

    data = json.loads(log_file.read_text())

    expected_keys = {
        "timestamp",
        "level",
        "context",
        "message",
        "module",
        "function",
        "line",
    }

    assert expected_keys.issubset(data.keys())


def test_color_formatter_does_not_break_text_output(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify that ColorFormatter produces well-formed text output.

    We do NOT assert ANSI sequences directly—just ensure formatting works.
    """
    logger = logging.getLogger("cloud_autopkg_runner.test_color")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    handler = logging.StreamHandler()
    formatter = ColorFormatter("%(levelname)-7s %(message)s")
    handler.setFormatter(formatter)

    logger.addHandler(handler)

    with caplog.at_level(logging.INFO, logger=logger.name):
        logger.info("color test")

    # caplog records the *uncolored* message, formatter colors only the handler stream
    assert "color test" in caplog.text
    assert "INFO" in caplog.text


def test_text_and_json_handlers_can_coexist(tmp_path: Path) -> None:
    """Ensure that text console output and JSON file output work together."""
    log_file = tmp_path / "combo.json"

    logging_config.initialize_logger(
        verbosity_level=2,
        log_file=str(log_file),
        log_format="json",
    )

    logger = logging.getLogger("cloud_autopkg_runner")

    # Should hit both console and json file handler
    logger.info("combo test")

    # Verify file received JSON
    data = json.loads(log_file.read_text())
    assert data["message"] == "combo test"
