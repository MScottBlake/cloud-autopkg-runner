import asyncio
import sys
from pathlib import Path

import pytest

from cloud_autopkg_runner import shell
from cloud_autopkg_runner.exceptions import ShellCommandError

# Portable long-running command; `sleep` is unavailable on Windows.
SLEEP_CMD = [sys.executable, "-c", "import time; time.sleep(30)"]


@pytest.mark.asyncio
async def test_run_cmd_success() -> None:
    """Test successful command execution."""
    returncode, stdout, stderr = await shell.run_cmd("echo 'Hello, world!'")
    assert returncode == 0
    assert "Hello, world!" in stdout
    assert not stderr


@pytest.mark.asyncio
async def test_run_cmd_failure() -> None:
    """Test command execution with a non-zero exit code."""
    with pytest.raises(ShellCommandError) as exc_info:
        await shell.run_cmd("false")
    assert "Command failed with exit code 1: false" in str(exc_info.value)


@pytest.mark.asyncio
async def test_run_cmd_no_check() -> None:
    """Test command execution with check=False."""
    returncode, stdout, stderr = await shell.run_cmd("false", check=False)
    assert returncode == 1
    assert not stdout
    assert not stderr


@pytest.mark.asyncio
async def test_run_cmd_capture_output_false() -> None:
    """Test command execution with capture_output=False."""
    returncode, stdout, stderr = await shell.run_cmd(
        "echo 'Hello, world!'", capture_output=False
    )
    assert returncode == 0
    assert not stdout
    assert not stderr


@pytest.mark.asyncio
async def test_run_cmd_cwd(tmp_path: Path) -> None:
    """Test command execution with a specified working directory."""
    # Create a file in the temporary directory
    test_file = tmp_path / "test.txt"
    test_file.write_text("Test content")

    # Run a command that reads the file in the temporary directory
    returncode, stdout, stderr = await shell.run_cmd(
        f"cat {test_file}", cwd=str(tmp_path)
    )
    assert returncode == 0
    assert "Test content" in stdout
    assert not stderr


@pytest.mark.asyncio
async def test_run_cmd_timeout() -> None:
    """Test command execution with a timeout."""
    with pytest.raises(ShellCommandError) as exc_info:
        await shell.run_cmd("sleep 2", timeout=1)
    assert "Command failed with exit code -1: sleep 2" in str(exc_info.value)


@pytest.mark.asyncio
async def test_run_cmd_command_not_found() -> None:
    """Test command execution when the command is not found."""
    with pytest.raises(ShellCommandError) as exc_info:
        await shell.run_cmd("nonexistent_command")
    assert "Command not found: nonexistent_command" in str(exc_info.value)


@pytest.mark.asyncio
async def test_run_cmd_shell_injection_safe() -> None:
    """Test that shell.run_cmd is safe from shell injection."""
    # Attempt to inject a command using a semicolon
    returncode, stdout, stderr = await shell.run_cmd(
        "echo 'hello; rm -rf /'", check=False
    )  # Removed injection
    assert returncode == 0
    assert "hello; rm -rf /" in stdout  # Injection is treated as literal
    assert not stderr

    # If the above test is not working as expected due to shell
    # injection (which it shouldn't with create_subprocess_exec),
    # create a file named 'hello; rm -rf /' and check if it exists.
    # It should *not* exist because the injection should not have worked.
    file_path = Path("hello; rm -rf /")
    assert not file_path.exists()


@pytest.mark.asyncio
async def test_run_cmd_list_command() -> None:
    """Test command execution with a list command."""
    returncode, stdout, stderr = await shell.run_cmd(["echo", "Hello, world!"])
    assert returncode == 0
    assert "Hello, world!" in stdout
    assert not stderr


@pytest.mark.asyncio
async def test_run_cmd_file_not_found_error(tmp_path: Path) -> None:
    """Test FileNotFoundError when the command tries to access a non-existent file."""
    # Create a temporary directory
    cwd = str(tmp_path)

    # Test running 'cat non_existent_file.txt' command in the directory
    with pytest.raises(ShellCommandError) as exc_info:
        await shell.run_cmd("cat non_existent_file.txt", cwd=cwd)
    assert "Command failed with exit code 1: cat non_existent_file.txt" in str(
        exc_info.value
    )


class ProcessTracker:
    """Wraps `create_subprocess_exec` so tests can inspect spawned processes."""

    def __init__(self) -> None:
        """Initialize the tracker and capture the real spawn function."""
        self.processes: list[asyncio.subprocess.Process] = []
        self.started = asyncio.Event()
        self._real_exec = asyncio.create_subprocess_exec

    async def exec(self, *args: object, **kwargs: object) -> object:
        """Spawn the process and record it.

        Returns:
            The spawned subprocess.
        """
        proc = await self._real_exec(*args, **kwargs)  # pyright: ignore[reportArgumentType]
        self.processes.append(proc)
        self.started.set()
        return proc


@pytest.mark.asyncio
@pytest.mark.parametrize("capture_output", [True, False])
async def test_run_cmd_kills_subprocess_when_cancelled(*, capture_output: bool) -> None:
    """Cancelling run_cmd must not leave the subprocess running."""
    tracker = ProcessTracker()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(asyncio, "create_subprocess_exec", tracker.exec)
        task = asyncio.create_task(
            shell.run_cmd(SLEEP_CMD, capture_output=capture_output)
        )
        await asyncio.wait_for(tracker.started.wait(), timeout=10)

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert len(tracker.processes) == 1
    await asyncio.wait_for(tracker.processes[0].wait(), timeout=10)
    assert tracker.processes[0].returncode is not None


@pytest.mark.asyncio
async def test_run_cmd_reaps_subprocess_on_timeout() -> None:
    """A timed-out command must be killed and reaped, not left running."""
    tracker = ProcessTracker()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(asyncio, "create_subprocess_exec", tracker.exec)
        returncode, _stdout, stderr = await shell.run_cmd(
            SLEEP_CMD, timeout=1, check=False
        )

    assert returncode == shell.TIMEOUT_RETURNCODE
    assert "timed out" in stderr
    assert tracker.processes[0].returncode is not None


@pytest.mark.asyncio
async def test_run_cmd_os_error() -> None:
    """Test OSError when the command encounters an OS-level error."""
    # Use an invalid command that will cause an OSError
    with pytest.raises(ShellCommandError) as exc_info:
        await shell.run_cmd("/dev/null")
    # Check if the error message contains "Permission denied" or "Not executable"
    assert "OS error" in str(exc_info.value)
