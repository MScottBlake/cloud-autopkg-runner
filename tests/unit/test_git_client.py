"""Pytest tests for the GitClient class in cloud-autopkg_runner.git_client."""

import shutil
from collections.abc import Generator
from logging import Logger
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cloud_autopkg_runner import GitClient
from cloud_autopkg_runner.exceptions import (
    GitDefaultBranchError,
    GitError,
    GitMergeError,
    GitRepoDoesNotExistError,
    GitWorktreeCreationError,
    GitWorktreeMissingPathError,
    GitWorktreeMoveError,
    PathNotGitRepoError,
    ShellCommandException,
)

# --- Fixtures ---


@pytest.fixture
def mock_run_cmd() -> Generator[MagicMock | AsyncMock, Any, None]:
    """Fixture to mock shell.run_cmd globally for tests using patch."""
    with patch("cloud_autopkg_runner.shell.run_cmd", new_callable=AsyncMock) as _mock:
        yield _mock


@pytest.fixture
def mock_logger() -> Generator[Logger, Any, None]:
    """Fixture to mock the logger to prevent console output during tests."""
    with patch("cloud_autopkg_runner.logging_config.get_logger") as mock_get_logger:
        mock_logger_instance = mock_get_logger.return_value
        mock_logger_instance.debug = MagicMock()
        mock_logger_instance.info = MagicMock()
        mock_logger_instance.warning = MagicMock()
        mock_logger_instance.error = MagicMock()
        mock_logger_instance.critical = MagicMock()
        yield mock_logger_instance


@pytest.fixture
def tmp_repo_path(tmp_path: Path) -> Generator[Path, None]:
    """Provides a temporary path for a Git repository, ensuring cleanup."""
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir(exist_ok=True)
    (repo_path / ".git").mkdir(exist_ok=True)
    yield repo_path
    if repo_path.exists():
        shutil.rmtree(repo_path)


# @pytest.fixture
#     """Fixture to create a temporary directory structured like a Git repository."""
#     repo_dir = tmp_path / "test_git_repo"
#     repo_dir.mkdir()
#     (repo_dir / ".git").mkdir()  # Simulate a .git directory
#     return repo_dir


@pytest.fixture
def non_git_path(tmp_path: Path) -> Path:
    """Fixture to create a temporary directory that is NOT a Git repository."""
    non_git_dir = tmp_path / "non_git_dir"
    non_git_dir.mkdir()
    return non_git_dir


@pytest.fixture
def git_client_instance(tmp_repo_path: Path) -> GitClient:
    """Fixture to provide an initialized GitClient instance for tests."""
    return GitClient(tmp_repo_path)


# --- Test __init__ ---


@pytest.mark.asyncio
async def test_init_success(tmp_repo_path: Path) -> None:
    """Test GitClient initialization with a valid, existing path."""
    client = GitClient(tmp_repo_path)
    assert client.repo_path == tmp_repo_path.resolve()


@pytest.mark.asyncio
async def test_init_raises_git_repo_does_not_exist_error(tmp_path: Path) -> None:
    """Test GitClient initialization with a non-existent path."""
    non_existent_path = tmp_path / "non_existent_repo_xyz"
    assert not non_existent_path.exists()  # Ensure it doesn't exist initially

    with pytest.raises(GitRepoDoesNotExistError) as exc_info:
        GitClient(non_existent_path)
    assert str(non_existent_path) in str(exc_info.value)


@pytest.mark.asyncio
async def test_init_raises_git_repo_does_not_exist_error_if_not_directory(
    tmp_repo_path: Path,
) -> None:
    """Test GitClient initialization with a path to a file."""
    test_file = tmp_repo_path / "test_file.txt"
    test_file.touch()  # Create a file
    # The current __init__ checks `is_dir()`. If it's a file, is_dir() is False,
    # which leads to GitRepoDoesNotExistError.
    with pytest.raises(GitRepoDoesNotExistError) as exc_info:
        GitClient(test_file)
    assert "Repository path does not exist:" in str(exc_info.value)


# --- Test _run_git_cmd ---


@pytest.mark.asyncio
async def test_run_git_cmd_success(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock
) -> None:
    """Test _run_git_cmd for successful execution."""
    mock_run_cmd.return_value = (0, "stdout content", "stderr content")
    returncode, stdout, stderr = await git_client_instance._run_git_cmd(["status"])
    assert returncode == 0
    assert stdout == "stdout content"
    assert stderr == "stderr content"
    mock_run_cmd.assert_awaited_once_with(
        ["git", "status"],
        cwd=str(git_client_instance.repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )


@pytest.mark.asyncio
async def test_run_git_cmd_raises_git_error_on_shell_command_exception(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock
) -> None:
    """Test _run_git_cmd re-raises ShellCommandException as GitError."""
    mock_run_cmd.side_effect = ShellCommandException("mock error")
    with pytest.raises(GitError) as exc_info:
        await git_client_instance._run_git_cmd(["status"])
    assert "git status" in str(exc_info.value)


@pytest.mark.asyncio
async def test_run_git_cmd_raises_git_repo_does_not_exist_error_if_cwd_non_existent(
    git_client_instance: GitClient, tmp_path: Path
) -> None:
    """Test _run_git_cmd raises GitRepoDoesNotExistError if cwd is non-existent."""
    non_existent_cwd = tmp_path / "non_existent_cwd_for_git_cmd"
    assert not non_existent_cwd.exists()

    with pytest.raises(GitRepoDoesNotExistError) as exc_info:
        await git_client_instance._run_git_cmd(["status"], cwd=non_existent_cwd)
    assert str(non_existent_cwd) in str(exc_info.value)


# --- Test _check_is_git_repo ---


@pytest.mark.asyncio
async def test_check_is_git_repo_success(git_client_instance: GitClient) -> None:
    """Test _check_is_git_repo with a valid Git repository."""
    # No exception should be raised. The fixture provides a valid repo.
    await git_client_instance._check_is_git_repo(git_client_instance.repo_path)


@pytest.mark.asyncio
async def test_check_is_git_repo_raises_git_repo_does_not_exist_error(
    git_client_instance: GitClient, tmp_path: Path
) -> None:
    """Test _check_is_git_repo with a non-existent path."""
    non_existent_path = tmp_path / "non_existent_check_repo_xyz"
    assert not non_existent_path.exists()

    with pytest.raises(GitRepoDoesNotExistError) as exc_info:
        await git_client_instance._check_is_git_repo(non_existent_path)
    assert str(non_existent_path) in str(exc_info.value)


@pytest.mark.asyncio
async def test_check_is_git_repo_raises_path_not_git_repo_error(
    git_client_instance: GitClient,
) -> None:
    """Test _check_is_git_repo with an existing path that is not a Git repo."""
    # Remove the mock .git directory to simulate a non-Git repo
    (git_client_instance.repo_path / ".git").rmdir()
    with pytest.raises(PathNotGitRepoError) as exc_info:
        await git_client_instance._check_is_git_repo(git_client_instance.repo_path)
    assert "not appear to be a Git repository" in str(exc_info.value)


# --- Test init ---


@pytest.mark.asyncio
async def test_init_creates_repo(
    tmp_path: Path, mock_run_cmd: AsyncMock, mock_logger: Logger
) -> None:
    """Test init command successfully initializes a new repository."""
    new_repo_path = tmp_path / "new_git_repo_for_init_test"
    if new_repo_path.exists():
        new_repo_path.unlink()
    assert not new_repo_path.exists()

    # To instantiate GitClient, new_repo_path must be a directory.
    # So we create the physical directory first for __init__ to pass.
    new_repo_path.mkdir(parents=True, exist_ok=True)

    client = GitClient(new_repo_path)

    # In this scenario, `client.repo_path.exists()` will return True naturally.
    # So `client.repo_path.mkdir()` should NOT be called by the init method.
    mock_run_cmd.return_value = (0, "", "")

    await client.init(initial_branch="main")

    mock_run_cmd.assert_awaited_once_with(
        ["git", "init", "-b", "main"],
        cwd=str(new_repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )
    mock_logger.info.assert_called_with(
        "Initializing Git repository at %s...", new_repo_path
    )


@pytest.mark.asyncio
async def test_init_with_bare(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock
) -> None:
    """Test init command with bare option."""
    mock_run_cmd.return_value = (0, "", "")
    await git_client_instance.init(bare=True)
    mock_run_cmd.assert_awaited_once_with(
        ["git", "init", "--bare"],
        cwd=str(git_client_instance.repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )


# --- Test add ---


@pytest.mark.asyncio
async def test_add_single_file(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock
) -> None:
    """Test add command with a single file."""
    mock_run_cmd.return_value = (0, "", "")
    await git_client_instance.add("file.txt")
    mock_run_cmd.assert_awaited_once_with(
        ["git", "add", "file.txt"],
        cwd=str(git_client_instance.repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )


@pytest.mark.asyncio
async def test_add_multiple_files(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock
) -> None:
    """Test add command with multiple files and options."""
    mock_run_cmd.return_value = (0, "", "")
    await git_client_instance.add(["file1.txt", "file2.txt"], force=True, update=True)
    mock_run_cmd.assert_awaited_once_with(
        ["git", "add", "--force", "--update", "file1.txt", "file2.txt"],
        cwd=str(git_client_instance.repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )


# --- Test commit ---


@pytest.mark.asyncio
async def test_commit_basic(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock
) -> None:
    """Test commit command with a basic message."""
    mock_run_cmd.return_value = (0, "", "")
    await git_client_instance.commit("Initial commit")
    mock_run_cmd.assert_awaited_once_with(
        ["git", "commit", "-m", "Initial commit"],
        cwd=str(git_client_instance.repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )


@pytest.mark.asyncio
async def test_commit_with_all_options(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock
) -> None:
    """Test commit command with all optional arguments."""
    mock_run_cmd.return_value = (0, "", "")
    await git_client_instance.commit(
        "Test commit",
        allow_empty=True,
        all_changes=True,
        no_verify=True,
        amend=True,
        author="Test Author <test@example.com>",
    )
    mock_run_cmd.assert_awaited_once_with(
        [
            "git",
            "commit",
            "-m",
            "Test commit",
            "--allow-empty",
            "--all",
            "--no-verify",
            "--amend",
            "--author=Test Author <test@example.com>",
        ],
        cwd=str(git_client_instance.repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )


# --- Test branch ---


@pytest.mark.asyncio
async def test_branch_create(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock
) -> None:
    """Test branch command to create a new branch."""
    mock_run_cmd.return_value = (0, "", "")
    await git_client_instance.branch("new-feature")
    mock_run_cmd.assert_awaited_once_with(
        ["git", "branch", "new-feature"],
        cwd=str(git_client_instance.repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )


@pytest.mark.asyncio
async def test_branch_create_from_start_point(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock
) -> None:
    """Test branch command to create a branch from a specific start point."""
    mock_run_cmd.return_value = (0, "", "")
    await git_client_instance.branch("hotfix", start_point="main")
    mock_run_cmd.assert_awaited_once_with(
        ["git", "branch", "hotfix", "main"],
        cwd=str(git_client_instance.repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )


@pytest.mark.asyncio
async def test_branch_create_force(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock
) -> None:
    """Test branch command with force option."""
    mock_run_cmd.return_value = (0, "", "")
    await git_client_instance.branch("existing-branch", force=True)
    mock_run_cmd.assert_awaited_once_with(
        ["git", "branch", "--force", "existing-branch"],
        cwd=str(git_client_instance.repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )


# --- Test merge_branch ---


@pytest.mark.asyncio
async def test_merge_branch_success(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock
) -> None:
    """Test merge_branch successfully merges a branch."""
    mock_run_cmd.side_effect = [
        (0, "main\n", ""),  # For get_current_branch: 'main'
        (0, "", ""),  # For merge command
    ]
    await git_client_instance.merge_branch("feature-x", target_branch="main")
    mock_run_cmd.assert_any_call(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=str(git_client_instance.repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )
    mock_run_cmd.assert_called_with(
        ["git", "merge", "feature-x"],
        cwd=str(git_client_instance.repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )


@pytest.mark.asyncio
async def test_merge_branch_raises_git_merge_error_if_target_not_checked_out(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock
) -> None:
    """Test merge_branch raises GitMergeError if target branch is not current."""
    mock_run_cmd.return_value = (0, "dev\n", "")  # current branch is 'dev'
    with pytest.raises(GitMergeError) as exc_info:
        await git_client_instance.merge_branch("feature-x", target_branch="main")
    assert (
        "Cannot merge: 'main' is not currently checked out. Current branch is 'dev'."
        in str(exc_info.value)
    )
    mock_run_cmd.assert_awaited_once_with(  # Assert that get_current_branch was called
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=str(git_client_instance.repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )


@pytest.mark.asyncio
async def test_merge_branch_with_no_ff_and_no_edit(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock
) -> None:
    """Test merge_branch with --no-ff and --no-edit options."""
    mock_run_cmd.side_effect = [
        (0, "main\n", ""),  # For get_current_branch
        (0, "", ""),  # For merge command
    ]
    await git_client_instance.merge_branch(
        "feature-y", target_branch="main", no_ff=True, no_edit=True
    )
    mock_run_cmd.assert_called_with(
        ["git", "merge", "--no-ff", "--no-edit", "feature-y"],
        cwd=str(git_client_instance.repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )


@pytest.mark.asyncio
async def test_merge_branch_with_squash(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock
) -> None:
    """Test merge_branch with --squash option."""
    mock_run_cmd.side_effect = [
        (0, "main\n", ""),  # For get_current_branch
        (0, "", ""),  # For merge command
    ]
    await git_client_instance.merge_branch(
        "feature-z", target_branch="main", squash=True
    )
    mock_run_cmd.assert_called_with(
        ["git", "merge", "--squash", "feature-z"],
        cwd=str(git_client_instance.repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )


@pytest.mark.asyncio
async def test_merge_branch_target_is_head(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock
) -> None:
    """Test merge_branch when target_branch is 'HEAD' (no current branch check)."""
    mock_run_cmd.return_value = (0, "", "")  # Only for the merge command
    await git_client_instance.merge_branch("another-feature", target_branch="HEAD")
    # No call to get_current_branch should happen
    mock_run_cmd.assert_called_once_with(
        ["git", "merge", "another-feature"],
        cwd=str(git_client_instance.repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )


# --- Test checkout ---


@pytest.mark.asyncio
async def test_checkout_branch(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock
) -> None:
    """Test checkout command to switch to an existing branch."""
    mock_run_cmd.return_value = (0, "", "")
    await git_client_instance.checkout("existing-branch")
    mock_run_cmd.assert_awaited_once_with(
        ["git", "checkout", "existing-branch"],
        cwd=str(git_client_instance.repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )


@pytest.mark.asyncio
async def test_checkout_new_branch(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock
) -> None:
    """Test checkout command to create and switch to a new branch."""
    mock_run_cmd.return_value = (0, "", "")
    await git_client_instance.checkout("new-branch-checkout", create_branch=True)
    mock_run_cmd.assert_awaited_once_with(
        ["git", "checkout", "-b", "new-branch-checkout"],
        cwd=str(git_client_instance.repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )


# --- Test fetch ---


@pytest.mark.asyncio
async def test_fetch_default(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock
) -> None:
    """Test fetch command without specific remote."""
    mock_run_cmd.return_value = (0, "", "")
    await git_client_instance.fetch()
    mock_run_cmd.assert_awaited_once_with(
        ["git", "fetch"],
        cwd=str(git_client_instance.repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )


@pytest.mark.asyncio
async def test_fetch_with_options(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock
) -> None:
    """Test fetch command with remote and various options."""
    mock_run_cmd.return_value = (0, "", "")
    await git_client_instance.fetch("origin", prune=True, all_remotes=True, tags=True)
    mock_run_cmd.assert_awaited_once_with(
        ["git", "fetch", "--prune", "--all", "--tags", "origin"],
        cwd=str(git_client_instance.repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )


# --- Test pull ---


@pytest.mark.asyncio
async def test_pull_default(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock
) -> None:
    """Test pull command without specific remote/branch."""
    mock_run_cmd.return_value = (0, "", "")
    await git_client_instance.pull()
    mock_run_cmd.assert_awaited_once_with(
        ["git", "pull"],
        cwd=str(git_client_instance.repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )


@pytest.mark.asyncio
async def test_pull_with_rebase(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock
) -> None:
    """Test pull command with rebase option."""
    mock_run_cmd.return_value = (0, "", "")
    await git_client_instance.pull("origin", "main", rebase=True)
    mock_run_cmd.assert_awaited_once_with(
        ["git", "pull", "--rebase", "origin", "main"],
        cwd=str(git_client_instance.repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )


# --- Test push ---


@pytest.mark.asyncio
async def test_push_default(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock
) -> None:
    """Test push command without specific remote/branch."""
    mock_run_cmd.return_value = (0, "", "")
    await git_client_instance.push()
    mock_run_cmd.assert_awaited_once_with(
        ["git", "push"],
        cwd=str(git_client_instance.repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )


@pytest.mark.asyncio
async def test_push_with_force_and_set_upstream(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock
) -> None:
    """Test push command with force and set_upstream options."""
    mock_run_cmd.return_value = (0, "", "")
    await git_client_instance.push(
        "origin", "feature-branch", force=True, set_upstream=True
    )
    mock_run_cmd.assert_awaited_once_with(
        ["git", "push", "--force", "--set-upstream", "origin", "feature-branch"],
        cwd=str(git_client_instance.repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )


# --- Test status ---


@pytest.mark.asyncio
async def test_status_default(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock
) -> None:
    """Test status command returns expected output."""
    expected_output = "M README.md"
    mock_run_cmd.return_value = (0, expected_output, "")
    status = await git_client_instance.status()
    assert status == expected_output
    mock_run_cmd.assert_awaited_once_with(
        ["git", "status"],
        cwd=str(git_client_instance.repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )


@pytest.mark.asyncio
async def test_status_porcelain(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock
) -> None:
    """Test status command with porcelain option."""
    expected_output = " M README.md"
    mock_run_cmd.return_value = (0, expected_output, "")
    status = await git_client_instance.status(porcelain=True)
    assert status == expected_output
    mock_run_cmd.assert_awaited_once_with(
        ["git", "status", "--porcelain"],
        cwd=str(git_client_instance.repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )


# --- Test get_current_branch ---


@pytest.mark.asyncio
async def test_get_current_branch_success(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock
) -> None:
    """Test get_current_branch returns the correct branch name."""
    mock_run_cmd.return_value = (0, "main\n", "")
    branch = await git_client_instance.get_current_branch()
    assert branch == "main"
    mock_run_cmd.assert_awaited_once_with(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=str(git_client_instance.repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )


@pytest.mark.asyncio
async def test_get_current_branch_error(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock
) -> None:
    """Test get_current_branch raises GitError on underlying failure."""
    mock_run_cmd.side_effect = ShellCommandException("mock error")
    with pytest.raises(GitError):
        await git_client_instance.get_current_branch()


# --- Test get_default_branch ---


@pytest.mark.asyncio
async def test_get_default_branch_success_main(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock
) -> None:
    """Test get_default_branch correctly identifies 'main' as default."""
    mock_output = """* remote origin
  Fetch URL: git@github.com:user/repo.git
  Push  URL: git@github.com:user/repo.git
  HEAD branch: main
  Remote branches:
    main tracked
    feature tracked
  Local branch configured for 'git pull':
    main merges with remote main
  Local ref configured for 'git push':
    main pushes to remote main (up to date)
"""
    mock_run_cmd.return_value = (0, mock_output, "")
    default_branch = await git_client_instance.get_default_branch("origin")
    assert default_branch == "main"
    mock_run_cmd.assert_awaited_once_with(
        ["git", "remote", "show", "origin"],
        cwd=str(git_client_instance.repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )


@pytest.mark.asyncio
async def test_get_default_branch_success_master(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock
) -> None:
    """Test get_default_branch correctly identifies 'master' as default."""
    mock_output = """* remote upstream
  Fetch URL: https://github.com/another/repo.git
  Push  URL: https://github.com/another/repo.git
  HEAD branch: master
"""
    mock_run_cmd.return_value = (0, mock_output, "")
    default_branch = await git_client_instance.get_default_branch("upstream")
    assert default_branch == "master"


@pytest.mark.asyncio
async def test_get_default_branch_raises_git_default_branch_error_no_head_branch_line(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock
) -> None:
    """Test get_default_branch raises error if 'HEAD branch' line is missing."""
    mock_output = """* remote origin
  Fetch URL: git@github.com:user/repo.git
"""
    mock_run_cmd.return_value = (0, mock_output, "")
    with pytest.raises(GitDefaultBranchError) as exc_info:
        await git_client_instance.get_default_branch("origin")
    assert "Could not determine default branch for remote 'origin'" in str(
        exc_info.value
    )


@pytest.mark.asyncio
async def test_get_default_branch_raises_git_error_on_underlying_failure(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock
) -> None:
    """Test get_default_branch raises GitError on underlying shell failure."""
    mock_run_cmd.side_effect = ShellCommandException("remote not found")
    with pytest.raises(GitError):
        await git_client_instance.get_default_branch("nonexistent")


# --- Test get_remote_url ---


@pytest.mark.asyncio
async def test_get_remote_url_success(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock
) -> None:
    """Test get_remote_url returns the correct URL."""
    mock_run_cmd.return_value = (0, "https://github.com/user/repo.git\n", "")
    url = await git_client_instance.get_remote_url("origin")
    assert url == "https://github.com/user/repo.git"
    mock_run_cmd.assert_awaited_once_with(
        ["git", "remote", "get-url", "origin"],
        cwd=str(git_client_instance.repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )


# --- Test add_remote ---


@pytest.mark.asyncio
async def test_add_remote_success(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock
) -> None:
    """Test add_remote command successfully adds a remote."""
    mock_run_cmd.return_value = (0, "", "")
    await git_client_instance.add_remote(
        "upstream", "https://github.com/upstream/repo.git"
    )
    mock_run_cmd.assert_awaited_once_with(
        ["git", "remote", "add", "upstream", "https://github.com/upstream/repo.git"],
        cwd=str(git_client_instance.repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )


@pytest.mark.asyncio
async def test_add_remote_with_track_branches(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock
) -> None:
    """Test add_remote command with track_branches option."""
    mock_run_cmd.return_value = (0, "", "")
    await git_client_instance.add_remote(
        "myremote", "ssh://git@host/path.git", track_branches=["dev", "prod"]
    )
    mock_run_cmd.assert_awaited_once_with(
        [
            "git",
            "remote",
            "add",
            "-t",
            "dev",
            "-t",
            "prod",
            "myremote",
            "ssh://git@host/path.git",
        ],
        cwd=str(git_client_instance.repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )


# --- Test add_worktree ---


@pytest.mark.asyncio
async def test_add_worktree_success(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock, tmp_repo_path: Path
) -> None:
    """Test add_worktree successfully creates a worktree."""
    mock_run_cmd.return_value = (0, "", "")

    created_path = await git_client_instance.add_worktree(
        tmp_repo_path, "feature-branch"
    )

    assert created_path == tmp_repo_path.resolve()
    mock_run_cmd.assert_awaited_once_with(
        ["git", "worktree", "add", str(tmp_repo_path), "feature-branch"],
        cwd=str(git_client_instance.repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )


@pytest.mark.asyncio
async def test_add_worktree_raises_creation_error_on_git_failure(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock, tmp_path: Path
) -> None:
    """Test add_worktree raises GitWorktreeCreationError on underlying Git failure."""
    worktree_path = tmp_path / "worktree_fail"
    mock_run_cmd.side_effect = ShellCommandException("git worktree add failed")

    with pytest.raises(GitWorktreeCreationError) as exc_info:
        await git_client_instance.add_worktree(worktree_path, "branch")
    assert f"Failed to create worktree at {worktree_path}" in str(exc_info.value)


@pytest.mark.asyncio
async def test_add_worktree_raises_creation_error_on_verification_failure(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock, tmp_path: Path
) -> None:
    """Test add_worktree raises GitWorktreeCreationError if worktree not verified."""
    worktree_path = tmp_path / "worktree_no_verify"

    mock_run_cmd.return_value = (0, "", "")  # Git command itself succeeds

    with pytest.raises(GitWorktreeCreationError) as exc_info:
        await git_client_instance.add_worktree(worktree_path, "branch")
    assert f"Failed to create worktree at {worktree_path}" in str(exc_info.value)


# --- Test list_worktrees ---


@pytest.mark.asyncio
async def test_list_worktrees_success_multiple(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock
) -> None:
    """Test list_worktrees correctly parses multiple worktrees."""
    mock_output = """worktree /path/to/repo
HEAD abcd1234abcd1234abcd1234abcd1234abcd1234
branch refs/heads/main
worktree /path/to/worktree1
HEAD efgh5678efgh5678efgh5678efgh5678efgh5678
branch refs/heads/feature/branch-x
worktree /path/to/worktree2
HEAD 1234abcd1234abcd1234abcd1234abcd1234abcd
"""
    mock_run_cmd.return_value = (0, mock_output, "")
    worktrees = await git_client_instance.list_worktrees()
    assert len(worktrees) == 3
    # Use .resolve() on the expected paths too for consistent comparison
    assert worktrees[0] == (Path("/path/to/repo").resolve(), "main")
    assert worktrees[1] == (Path("/path/to/worktree1").resolve(), "feature/branch-x")
    assert worktrees[2] == (
        Path("/path/to/worktree2").resolve(),
        "1234abcd1234abcd1234abcd1234abcd1234abcd",
    )
    mock_run_cmd.assert_awaited_once_with(
        ["git", "worktree", "list", "--porcelain"],
        cwd=str(git_client_instance.repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )


@pytest.mark.asyncio
async def test_list_worktrees_success_empty(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock
) -> None:
    """Test list_worktrees returns empty list for no worktrees."""
    mock_run_cmd.return_value = (0, "", "")  # Empty output
    worktrees = await git_client_instance.list_worktrees()
    assert len(worktrees) == 0
    mock_run_cmd.assert_awaited_once_with(
        ["git", "worktree", "list", "--porcelain"],
        cwd=str(git_client_instance.repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )


# --- Test remove_worktree ---


@pytest.mark.asyncio
async def test_remove_worktree_success(
    git_client_instance: GitClient,
    mock_run_cmd: AsyncMock,
    mock_logger: Logger,
    tmp_path: Path,
) -> None:
    """Test remove_worktree successfully removes a worktree."""
    worktree_path = tmp_path / "worktree_to_remove"
    worktree_path.mkdir(exist_ok=True)

    mock_run_cmd.return_value = (0, "", "")  # Git command succeeds

    await git_client_instance.remove_worktree(worktree_path)

    mock_run_cmd.assert_awaited_once_with(
        ["git", "worktree", "remove", str(worktree_path)],
        cwd=str(git_client_instance.repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )
    mock_logger.warning.assert_not_called()


@pytest.mark.asyncio
async def test_remove_worktree_with_force(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock, tmp_path: Path
) -> None:
    """Test remove_worktree with force option."""
    worktree_path = tmp_path / "worktree_to_remove_force"
    worktree_path.mkdir(exist_ok=True)

    mock_run_cmd.return_value = (0, "", "")
    await git_client_instance.remove_worktree(worktree_path, force=True)

    mock_run_cmd.assert_awaited_once_with(
        ["git", "worktree", "remove", "--force", str(worktree_path)],
        cwd=str(git_client_instance.repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )


@pytest.mark.asyncio
async def test_remove_worktree_warns_if_dir_remains(
    git_client_instance: GitClient,
    mock_run_cmd: AsyncMock,
    tmp_path: Path,
) -> None:
    """Test remove_worktree warns if directory still exists after command."""
    worktree_path = tmp_path / "worktree_remains"
    worktree_path.mkdir(exist_ok=True)
    mock_run_cmd.return_value = (0, "", "")

    await git_client_instance.remove_worktree(worktree_path)
    assert worktree_path.exists()


# --- Test prune_worktrees ---


@pytest.mark.asyncio
async def test_prune_worktrees_success(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock
) -> None:
    """Test prune_worktrees command successfully."""
    mock_run_cmd.return_value = (0, "", "")
    await git_client_instance.prune_worktrees()
    mock_run_cmd.assert_awaited_once_with(
        ["git", "worktree", "prune"],
        cwd=str(git_client_instance.repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )


# --- Test move_worktree ---


@pytest.mark.asyncio
async def test_move_worktree_raises_missing_path_error_if_old_path_non_existent(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock, tmp_path: Path
) -> None:
    """Test move_worktree raises error if old path doesn't exist."""
    old_path = tmp_path / "non_existent_old"
    new_path = tmp_path / "new"
    # Do not create old_path, so its .is_dir() will return False naturally.
    assert not old_path.is_dir()

    with pytest.raises(GitWorktreeMissingPathError) as exc_info:
        await git_client_instance.move_worktree(old_path, new_path)
    assert f"Worktree directory does not exist: {old_path}" in str(exc_info.value)
    mock_run_cmd.assert_not_awaited()  # Git command should not be called


@pytest.mark.asyncio
async def test_move_worktree_raises_move_error_on_git_failure(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock, tmp_path: Path
) -> None:
    """Test move_worktree raises GitWorktreeMoveError on underlying Git failure."""
    old_path = tmp_path / "old"
    new_path = tmp_path / "new"
    old_path.mkdir(
        parents=True, exist_ok=True
    )  # Ensure old_path exists for is_dir check

    mock_run_cmd.side_effect = ShellCommandException(
        "git move failed"
    )  # Simulate Git command failure

    with pytest.raises(GitWorktreeMoveError) as exc_info:
        await git_client_instance.move_worktree(old_path, new_path)
    assert f"Failed to move worktree from {old_path} to {new_path}" in str(
        exc_info.value
    )


@pytest.mark.asyncio
async def test_move_worktree_raises_move_error_on_verification_failure(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock, tmp_path: Path
) -> None:
    """Test move_worktree raises error if verification fails after move."""
    old_path = tmp_path / "old_no_verify"
    new_path = tmp_path / "new_no_verify"
    old_path.mkdir(parents=True, exist_ok=True)

    mock_run_cmd.return_value = (0, "", "")

    with pytest.raises(GitWorktreeMoveError) as exc_info:
        await git_client_instance.move_worktree(old_path, new_path)

    assert f"Failed to move worktree from {old_path} to {new_path}" in str(
        exc_info.value
    )
    assert old_path.exists()
    assert not new_path.exists()


# --- Test lock_worktree ---


@pytest.mark.asyncio
async def test_lock_worktree_success(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock, tmp_path: Path
) -> None:
    """Test lock_worktree successfully locks a worktree."""
    worktree_path = tmp_path / "locked_worktree"  # Use tmp_path for consistency
    worktree_path.mkdir(
        exist_ok=True
    )  # Ensure this path exists and is a directory for validation

    mock_run_cmd.return_value = (0, "", "")
    await git_client_instance.lock_worktree(worktree_path)
    mock_run_cmd.assert_awaited_once_with(
        ["git", "worktree", "lock", str(worktree_path)],
        cwd=str(git_client_instance.repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )


@pytest.mark.asyncio
async def test_lock_worktree_with_reason(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock, tmp_path: Path
) -> None:
    """Test lock_worktree with a reason."""
    worktree_path = tmp_path / "locked_worktree_reason"
    worktree_path.mkdir(exist_ok=True)

    mock_run_cmd.return_value = (0, "", "")
    await git_client_instance.lock_worktree(worktree_path, reason="Important work")
    mock_run_cmd.assert_awaited_once_with(
        ["git", "worktree", "lock", str(worktree_path), "--reason", "Important work"],
        cwd=str(git_client_instance.repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )


# --- Test unlock_worktree ---


@pytest.mark.asyncio
async def test_unlock_worktree_success(
    git_client_instance: GitClient, mock_run_cmd: AsyncMock, tmp_path: Path
) -> None:
    """Test unlock_worktree successfully unlocks a worktree."""
    worktree_path = tmp_path / "unlocked_worktree"
    worktree_path.mkdir(exist_ok=True)

    mock_run_cmd.return_value = (0, "", "")
    await git_client_instance.unlock_worktree(worktree_path)
    mock_run_cmd.assert_awaited_once_with(
        ["git", "worktree", "unlock", str(worktree_path)],
        cwd=str(git_client_instance.repo_path),
        check=True,
        capture_output=True,
        timeout=None,
    )
