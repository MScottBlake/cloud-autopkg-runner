"""Module for executing shell commands asynchronously in cloud-autopkg-runner.

This module provides functions for running shell commands in a non-blocking
manner, capturing their output, and handling errors. It is used to
interact with external tools and processes during AutoPkg workflows.
"""

import asyncio
import contextlib
import shlex

from cloud_autopkg_runner import logger
from cloud_autopkg_runner.exceptions import ShellCommandException


def _normalize_cmd(cmd: str | list[str]) -> list[str]:
    """Normalizes a command into a list of strings.

    If the command is a string, it is split into a list of strings using
    `shlex.split()`. If the command is already a list, it is returned as is.

    Args:
        cmd: The command to normalize. Can be a string or a list of strings.

    Returns:
        A list of strings representing the normalized command.

    Raises:
        ShellCommandException: If the command string is invalid and cannot be
            parsed by `shlex.split()`.
    """
    if not isinstance(cmd, str):
        return cmd

    try:
        return shlex.split(cmd)
    except ValueError as exc:
        raise ShellCommandException(  # noqa: TRY003
            f"Invalid command string: {cmd}. Error: {exc}"
        ) from exc


async def _run_and_capture(
    cmd: list[str],
    *,
    cwd: str | None = None,
    timeout: int | None = None,
) -> tuple[int, str, str]:
    """Runs a command in a subprocess and captures its output.

    Args:
        cmd: A list of strings representing the command to execute.
        cwd: An optional working directory for the command. If `None`, the
            current working directory is used.
        timeout: An optional timeout in seconds. If the command exceeds this
            timeout, it will be terminated.

    Returns:
        A tuple containing:
            - returncode (int): The exit code of the command.
            - stdout (str): The standard output of the command.
            - stderr (str): The standard error of the command.
    """
    returncode: int = -1

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        async with asyncio.timeout(timeout):
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")

            logger.debug(f"Command output:\n{stdout}\n{stderr}")

    except TimeoutError:
        logger.warning(f"Command timed out: {' '.join(cmd)}")
        if proc.returncode is None:  # Process still running
            with contextlib.suppress(ProcessLookupError):
                proc.kill()

        stdout = ""
        stderr = f"Command timed out after {timeout} seconds."

    returncode = proc.returncode if proc.returncode is not None else -1

    return returncode, stdout, stderr


async def _run_without_capture(
    cmd: list[str],
    *,
    cwd: str | None = None,
    timeout: int | None = None,
) -> tuple[int, str, str]:
    """Runs a command in a subprocess without capturing its output.

    Args:
        cmd: A list of strings representing the command to execute.
        cwd: An optional working directory for the command. If `None`, the
            current working directory is used.
        timeout: An optional timeout in seconds. If the command exceeds this
            timeout, it will be terminated.

    Returns:
        A tuple containing:
            - returncode (int): The exit code of the command.
            - stdout (str): An empty string ("").
            - stderr (str): An empty string ("").
    """
    returncode: int = -1

    proc = await asyncio.create_subprocess_exec(*cmd, cwd=cwd)

    try:
        async with asyncio.timeout(timeout):
            await asyncio.wait_for(proc.wait(), timeout=timeout)
    except TimeoutError:
        logger.warning(f"Command timed out: {' '.join(cmd)}")
        if proc.returncode is None:  # Process still running
            with contextlib.suppress(ProcessLookupError):
                proc.kill()

    returncode = proc.returncode if proc.returncode is not None else -1

    return returncode, "", ""


async def run_cmd(
    cmd: str | list[str],
    *,
    cwd: str | None = None,
    check: bool = True,
    capture_output: bool = True,
    timeout: int | None = None,
) -> tuple[int, str, str]:
    """Asynchronously executes a command in a subprocess.

    This function provides a robust and flexible way to run shell commands,
    capturing their output, and handling errors. It is used to interact
    with external tools and processes during AutoPkg workflows.

    Args:
        cmd: The command to execute. It can be provided as a string, which
            will be parsed using `shlex.split()`, or as a pre-split list of
            strings. Using a list is safer if you are constructing the command
            programmatically.
        cwd: An optional working directory to execute the command in. If `None`,
            the current working directory is used.
        check: A boolean value. If `True` (the default), a `ShellCommandException`
            is raised if the command returns a non-zero exit code. If `False`,
            the function will not raise an exception for non-zero exit codes, and
            the caller is responsible for checking the returned exit code.
        capture_output: A boolean value. If `True` (the default), the command's
            standard output and standard error are captured and returned as strings.
            If `False`, the command's output is directed to the parent process's
            standard output and standard error, and empty strings are returned for
            stdout and stderr.
        timeout: An optional integer specifying a timeout in seconds. If the command
            exceeds this timeout, it will be terminated, and the function will return
            a -1 returncode. If `None`, the command will run without a timeout.

    Returns:
        A tuple containing:
            - returncode (int): The exit code of the command. It will be -1 if the
              command times out or if another error prevents the process from
              completing.
            - stdout (str): The standard output of the command (if
              `capture_output` is `True`).
            - stderr (str): The standard error of the command (if
              `capture_output` is `True`).

    Raises:
        ShellCommandException: If any of the following occur:
            - The `cmd` string is invalid and cannot be parsed by `shlex.split()`.
            - The command returns a non-zero exit code and `check` is `True`.
            - A `FileNotFoundError` occurs (the command is not found).
            - An `OSError` occurs during subprocess creation.
            - Any other unexpected exception occurs during command execution.
    """
    cmd_list = _normalize_cmd(cmd)
    cmd_str = " ".join(cmd)

    logger.debug(f"Running command: {cmd_str}")
    if cwd:
        logger.debug(f"  in directory: {cwd}")

    try:
        if capture_output:
            returncode, stdout, stderr = await _run_and_capture(
                cmd_list, cwd=cwd, timeout=timeout
            )
        else:
            returncode, stdout, stderr = await _run_without_capture(
                cmd_list, cwd=cwd, timeout=timeout
            )
    except FileNotFoundError as exc:
        raise ShellCommandException(f"Command not found: {cmd_list[0]}") from exc  # noqa: TRY003
    except OSError as exc:
        raise ShellCommandException(  # noqa: TRY003
            f"OS error running command: {cmd_str}. Error: {exc}"
        ) from exc
    except Exception as exc:
        raise ShellCommandException(  # noqa: TRY003
            f"Unexpected error running command: {cmd_str}. Error: {exc}"
        ) from exc

    if check and returncode != 0:
        logger.error(f"Command failed: {cmd_str}")
        logger.error(f"  Exit code: {returncode}")
        logger.error(f"  Stdout: {stdout}")
        logger.error(f"  Stderr: {stderr}")
        raise ShellCommandException(  # noqa: TRY003
            f"Command failed with exit code {returncode}: {cmd_str}"
        )

    return returncode, stdout, stderr
