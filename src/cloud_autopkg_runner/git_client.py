"""Module for managing Git repositories and worktrees asynchronously.

This module provides a robust and asynchronous interface for performing common
Git operations, such as initializing, adding, committing, checking out branches,
and managing worktrees. It leverages the `shell` module for non-blocking
command execution and includes comprehensive error handling.
"""

from collections.abc import Sequence
from pathlib import Path

from cloud_autopkg_runner import logging_config, shell
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


class GitClient:
    """Manages Git repository operations and worktrees asynchronously.

    This class provides methods to interact with a Git repository, allowing
    for common Git commands and specific Git worktree management. All
    operations are asynchronous and non-blocking, making them suitable
    for integration into `asyncio` applications.

    Attributes:
        repo_path (Path): The path to the main Git repository.
        _logger (logging.Logger): The logger instance for this class.
    """

    def __init__(self, repo_path: str | Path) -> None:
        """Initializes the GitClient.

        Args:
            repo_path: The path to the main Git repository (absolute or relative).
                For a new repository, this is the path where the .git
                directory will be initialized.
        """
        self.repo_path = Path(repo_path).resolve()
        self._logger = logging_config.get_logger(__name__)

        if not self.repo_path.is_dir():
            raise GitRepoDoesNotExistError(self.repo_path)

    async def _run_git_cmd(
        self,
        subcommand: Sequence[str],
        *,
        cwd: str | Path | None = None,
        check: bool = True,
        capture_output: bool = True,
        timeout: int | None = None,
    ) -> tuple[int, str, str]:
        """Executes a Git command asynchronously.

        This private helper method forms the core of Git command execution.
        It constructs the full `git` command, sets the working directory,
        and handles potential `ShellCommandException` by re-raising them
        as `GitError` for consistent error handling within this class.

        Args:
            subcommand: A list of strings representing the Git subcommand
                and its arguments (e.g., `["init"]`, `["add", "."]`).
            cwd: The working directory for the command. Defaults to `self.repo_path`.
            check: If `True`, raises `ShellCommandException` on non-zero exit code.
                Set to `False` if you want to inspect the return code manually.
            capture_output: If `True`, captures stdout/stderr. If `False`,
                output is inherited from the parent process.
            timeout: Optional timeout in seconds for the command.

        Returns:
            A tuple containing:
                - returncode (int): The exit code of the command.
                - stdout (str): The standard output.
                - stderr (str): The standard error.

        Raises:
            GitError: If an underlying `ShellCommandException` occurs, or if
                the repository path does not exist when a Git command is attempted.
        """
        full_cmd = ["git", *subcommand]
        effective_cwd = Path(cwd).resolve() if cwd else self.repo_path

        if not effective_cwd.exists():
            raise GitRepoDoesNotExistError(effective_cwd)

        try:
            return await shell.run_cmd(
                full_cmd,
                cwd=str(effective_cwd),
                check=check,
                capture_output=capture_output,
                timeout=timeout,
            )
        except ShellCommandException as exc:
            raise GitError(" ".join(full_cmd)) from exc

    async def _check_is_git_repo(self, path: Path) -> None:
        """Checks if a given path is a valid Git repository.

        This private helper method performs a quick check by looking for
        the `.git` directory within the specified path. It raises specific
        exceptions if the path does not exist or is not a Git repository.

        Args:
            path: The path to check.

        Raises:
            GitRepoDoesNotExistError: If the path does not exist.
            PathNotGitRepoError: If the path exists but is not a Git repository.
        """
        if not path.is_dir():
            raise GitRepoDoesNotExistError(path)
        if not (path / ".git").exists():
            raise PathNotGitRepoError(path)

    async def init(
        self,
        *,
        bare: bool = False,
        initial_branch: str | None = None,
        timeout: int | None = None,
    ) -> None:
        """Initializes a new Git repository.

        Corresponds to `git init`. If `self.repo_path` does not exist,
        it will be created.

        Args:
            bare: If `True`, creates a bare repository (uses `--bare`).
            initial_branch: Specifies the name of the initial branch (uses `-b`).
                            Defaults to Git's default (usually 'master' or 'main').
            timeout: Optional timeout for the operation.

        Raises:
            GitError: If the repository initialization fails.
        """
        if not self.repo_path.exists():
            self._logger.debug("Creating directory for new repo: %s", self.repo_path)
            self.repo_path.mkdir(parents=True, exist_ok=True)

        cmd = ["init"]
        if bare:
            cmd.append("--bare")
        if initial_branch:
            cmd.extend(["-b", initial_branch])

        self._logger.info("Initializing Git repository at %s...", self.repo_path)
        await self._run_git_cmd(cmd, cwd=self.repo_path, timeout=timeout)

    async def add(
        self,
        paths: str | Sequence[str],
        *,
        force: bool = False,
        update: bool = False,
        timeout: int | None = None,
    ) -> None:
        """Adds file contents to the index.

        Corresponds to `git add <paths>`.

        Args:
            paths: A single path string or a list of path strings to add.
                   Use `"."` to add all changes in the current directory.
            force: Allows adding otherwise ignored files (uses `--force`).
            update: Only match files that are already indexed (uses `--update`).
            timeout: Optional timeout for the operation.

        Raises:
            GitError: If adding files to the index fails.
        """
        await self._check_is_git_repo(self.repo_path)

        cmd = ["add"]
        if force:
            cmd.append("--force")
        if update:
            cmd.append("--update")

        if isinstance(paths, str):
            cmd.append(paths)
        else:
            cmd.extend(paths)

        self._logger.info("Adding files to Git index in %s...", self.repo_path)
        await self._run_git_cmd(cmd, cwd=self.repo_path, timeout=timeout)

    async def commit(  # noqa: PLR0913
        self,
        message: str,
        *,
        allow_empty: bool = False,
        all_changes: bool = False,
        no_verify: bool = False,
        amend: bool = False,
        author: str | None = None,
        timeout: int | None = None,
    ) -> None:
        """Records changes to the repository.

        Corresponds to `git commit -m <message>`.

        Args:
            message: The commit message.
            allow_empty: If `True`, creates a commit even if there are no changes
                (uses `--allow-empty`).
            all_changes: If `True`, automatically stage files that have been
                modified and deleted (uses `--all` or `-a`).
            no_verify: If `True`, bypass pre-commit and commit-msg hooks
                (uses `--no-verify`).
            amend: If `True`, combines the latest commit with the current staged changes
                (uses `--amend`).
            author: Specifies the author for the commit in "Author Name <email>" format.
            timeout: Optional timeout for the operation.

        Raises:
            GitError: If the commit operation fails.
        """
        await self._check_is_git_repo(self.repo_path)

        cmd = ["commit", "-m", message]
        if allow_empty:
            cmd.append("--allow-empty")
        if all_changes:
            cmd.append("--all")
        if no_verify:
            cmd.append("--no-verify")
        if amend:
            cmd.append("--amend")
        if author:
            cmd.extend([f"--author={author}"])

        self._logger.info("Committing changes in %s...", self.repo_path)
        await self._run_git_cmd(cmd, cwd=self.repo_path, timeout=timeout)

    async def branch(
        self,
        branch_name: str,
        *,
        start_point: str | None = None,
        force: bool = False,
        timeout: int | None = None,
    ) -> None:
        """Creates a new branch.

        Corresponds to `git branch <branch_name> [start_point]`.

        Args:
            branch_name: The name of the new branch.
            start_point: The commit/branch/tag to start the new branch from.
                         If `None`, it starts from HEAD.
            force: If `True`, forces creation of the branch even if it already
                   exists (uses `--force`).
            timeout: Optional timeout for the operation.

        Raises:
            GitError: If branch creation fails.
        """
        await self._check_is_git_repo(self.repo_path)

        cmd = ["branch"]
        if force:
            cmd.append("--force")
        cmd.append(branch_name)
        if start_point:
            cmd.append(start_point)

        self._logger.info("Creating branch '%s' in %s...", branch_name, self.repo_path)
        await self._run_git_cmd(cmd, cwd=self.repo_path, timeout=timeout)

    async def merge_branch(  # noqa: PLR0913
        self,
        source_branch: str,
        target_branch: str = "HEAD",
        *,
        no_ff: bool = False,
        no_edit: bool = False,
        squash: bool = False,  # Added squash option
        timeout: int | None = None,
    ) -> None:
        """Merges a source branch into a target branch.

        Corresponds to `git merge <source_branch>`.
        The `target_branch` specifies which branch to merge *into* (defaults to current
        HEAD).

        Args:
            source_branch: The name of the branch to merge from.
            target_branch: The name of the branch to merge into. If "HEAD", merges into
                the current branch. The current branch must be `target_branch` when this
                method is called.
            no_ff: If `True`, always create a merge commit even if a fast-forward merge
                is possible (uses `--no-ff`).
            no_edit: If `True`, do not launch an editor for the merge commit message
                (uses `--no-edit`).
            squash: If `True`, combines all commits from the source branch into a
                single commit on the target branch (uses `--squash`). Note: This
                requires a subsequent manual `git commit`.
            timeout: Optional timeout for the operation.

        Raises:
            GitError: If the merge operation fails (e.g., conflicts, target branch not
                checked out).
        """
        await self._check_is_git_repo(self.repo_path)

        # Verify that target_branch is currently checked out, unless it is already HEAD
        if target_branch != "HEAD":
            current_branch = await self.get_current_branch()
            if current_branch != target_branch:
                raise GitMergeError(target_branch, current_branch)

        cmd = ["merge"]
        if no_ff:
            cmd.append("--no-ff")
        if no_edit:
            cmd.append("--no-edit")
        if squash:
            cmd.append("--squash")

        cmd.append(source_branch)

        self._logger.info(
            "Merging branch '%s' into '%s' in %s...",
            source_branch,
            target_branch,
            self.repo_path,
        )
        await self._run_git_cmd(cmd, cwd=self.repo_path, timeout=timeout)
        self._logger.info("Branch '%s' merged into '%s'.", source_branch, target_branch)

    async def checkout(
        self,
        ref: str,
        *,
        create_branch: bool = False,
        orphan: bool = False,
        timeout: int | None = None,
    ) -> None:
        """Switches branches or restores working tree files.

        Corresponds to `git checkout <ref>`.

        Args:
            ref: The branch, tag, or commit to checkout.
            create_branch: If `True`, creates a new branch named `ref` and checks it out
                (uses `-b`).
            orphan: If `True`, creates a new orphan branch (uses `--orphan`).
            timeout: Optional timeout for the operation.

        Raises:
            GitError: If checkout fails.
        """
        await self._check_is_git_repo(self.repo_path)

        cmd = ["checkout"]
        if create_branch:
            cmd.append("-b")
        if orphan:
            cmd.append("--orphan")
        cmd.append(ref)

        self._logger.info("Checking out '%s' in %s...", ref, self.repo_path)
        await self._run_git_cmd(cmd, cwd=self.repo_path, timeout=timeout)

    async def fetch(
        self,
        remote: str | None = None,
        *,
        prune: bool = False,
        all_remotes: bool = False,
        tags: bool = False,
        timeout: int | None = None,
    ) -> None:
        """Downloads objects and refs from another repository.

        Corresponds to `git fetch [remote]`.

        Args:
            remote: The name of the remote repository to fetch from. If `None`,
                    fetches from all remotes or the default remote.
            prune: If `True`, remove any remote-tracking branches which no
                   longer exist on the remote (uses `--prune`).
            all_remotes: If `True`, fetches all remotes (uses `--all`).
            tags: If `True`, fetches all tags from the remote (uses `--tags`).
            timeout: Optional timeout for the operation.

        Raises:
            GitError: If fetching fails.
        """
        await self._check_is_git_repo(self.repo_path)

        cmd = ["fetch"]
        if prune:
            cmd.append("--prune")
        if all_remotes:
            cmd.append("--all")
        if tags:
            cmd.append("--tags")
        if remote:
            cmd.append(remote)

        self._logger.info("Fetching from remote in %s...", self.repo_path)
        await self._run_git_cmd(cmd, cwd=self.repo_path, timeout=timeout)

    async def pull(
        self,
        remote: str | None = None,
        branch: str | None = None,
        *,
        rebase: bool = False,
        timeout: int | None = None,
    ) -> None:
        """Fetches from and integrates with another repository or a local branch.

        Corresponds to `git pull [remote] [branch]`.

        Args:
            remote: The remote repository to pull from.
            branch: The remote branch to pull.
            rebase: If `True`, rebase the current branch on top of the fetched
                    branch instead of merging (uses `--rebase`).
            timeout: Optional timeout for the operation.

        Raises:
            GitError: If pulling fails.
        """
        await self._check_is_git_repo(self.repo_path)

        cmd = ["pull"]
        if rebase:
            cmd.append("--rebase")
        if remote:
            cmd.append(remote)
        if branch:
            cmd.append(branch)

        self._logger.info("Pulling changes in %s...", self.repo_path)
        await self._run_git_cmd(cmd, cwd=self.repo_path, timeout=timeout)

    async def push(  # noqa: PLR0913
        self,
        remote: str | None = None,
        branch: str | None = None,
        *,
        force: bool = False,
        set_upstream: bool = False,
        push_options: Sequence[str] | None = None,
        timeout: int | None = None,
    ) -> None:
        """Pushes local commits to a remote repository.

        This corresponds to the `git push [remote] [branch]` command.

        Args:
            remote: Name or URL of the remote repository. If not provided,
                uses the default remote.
            branch: Name of the local branch to push. If not provided,
                pushes the current branch.
            force: Whether to force-push (`--force`), potentially overwriting
                remote history. **Use with caution.**
            set_upstream: Whether to set the upstream tracking reference
                (`--set-upstream`).
            push_options: Additional options to include in the push command
                (e.g., `['ci.skip']`).
            timeout: Optional timeout in seconds for the push operation.

        Raises:
            GitError: If the push operation fails or times out.
        """
        await self._check_is_git_repo(self.repo_path)

        cmd = ["push"]
        if force:
            cmd.append("--force")
        if set_upstream:
            cmd.append("--set-upstream")
        cmd.extend([f"--push-option={opt}" for opt in (push_options or [])])
        if remote:
            cmd.append(remote)
        if branch:
            cmd.append(branch)

        self._logger.info("Pushing changes from %s...", self.repo_path)
        await self._run_git_cmd(cmd, cwd=self.repo_path, timeout=timeout)

    async def status(
        self,
        *,
        short: bool = False,
        porcelain: bool = False,
        timeout: int | None = None,
    ) -> str:
        """Shows the working tree status.

        Corresponds to `git status`.

        Args:
            short: If `True`, gives the output in the short-format (uses `--short` or
                `-s`).
            porcelain: If `True`, gives the output in an easy-to-parse format
                designed for scripts (uses `--porcelain`).
            timeout: Optional timeout for the operation.

        Returns:
            The standard output of the `git status` command.

        Raises:
            GitError: If checking status fails.
        """
        await self._check_is_git_repo(self.repo_path)

        cmd = ["status"]
        if short:
            cmd.append("--short")
        if porcelain:
            cmd.append("--porcelain")

        self._logger.info("Checking Git status in %s...", self.repo_path)
        _returncode, stdout, _stderr = await self._run_git_cmd(
            cmd, cwd=self.repo_path, timeout=timeout
        )
        return stdout

    async def get_current_branch(self, timeout: int | None = None) -> str:
        """Gets the name of the current active branch.

        Corresponds to `git rev-parse --abbrev-ref HEAD`.

        Returns:
            The name of the current branch.

        Raises:
            GitError: If unable to determine the current branch.
        """
        await self._check_is_git_repo(self.repo_path)

        cmd = ["rev-parse", "--abbrev-ref", "HEAD"]

        self._logger.info("Getting current branch in %s...", self.repo_path)
        _returncode, stdout, _stderr = await self._run_git_cmd(
            cmd, cwd=self.repo_path, timeout=timeout
        )
        return stdout.strip()

    async def get_default_branch(
        self, remote_name: str = "origin", timeout: int | None = None
    ) -> str:
        """Gets the default branch name for a given remote.

        This typically queries the remote to find its HEAD reference.

        Corresponds to `git remote show <remote_name>`.

        Args:
            remote_name: The name of the remote (e.g., "origin").
            timeout: Optional timeout for the operation.

        Returns:
            The name of the default branch (e.g., 'main' or 'master').

        Raises:
            GitError: If unable to determine the default branch,
                or if the remote does not exist.
        """
        await self._check_is_git_repo(self.repo_path)

        cmd = ["remote", "show", remote_name]

        _returncode, stdout, _stderr = await self._run_git_cmd(
            cmd, cwd=self.repo_path, timeout=timeout
        )

        # Parse the output to find the "HEAD branch"
        for line in stdout.splitlines():
            if "HEAD branch:" in line:
                return line.split("HEAD branch:")[1].strip()

        raise GitDefaultBranchError(remote_name)

    async def get_remote_url(
        self, remote_name: str = "origin", timeout: int | None = None
    ) -> str:
        """Gets the URL of a specified remote.

        Corresponds to `git remote get-url <remote_name>`.

        Args:
            remote_name: The name of the remote (e.g., "origin").
            timeout: Optional timeout for the operation.

        Returns:
            The URL of the remote.

        Raises:
            GitError: If the remote URL cannot be retrieved.
        """
        await self._check_is_git_repo(self.repo_path)

        cmd = ["remote", "get-url", remote_name]

        self._logger.info(
            "Getting URL for remote '%s' in %s...", remote_name, self.repo_path
        )
        _returncode, stdout, _stderr = await self._run_git_cmd(
            cmd, cwd=self.repo_path, timeout=timeout
        )
        return stdout.strip()

    async def add_remote(
        self,
        name: str,
        url: str,
        *,
        track_branches: list[str] | None = None,
        timeout: int | None = None,
    ) -> None:
        """Adds a new remote repository.

        Corresponds to `git remote add <name> <url>`.

        Args:
            name: The name of the new remote.
            url: The URL of the remote repository.
            track_branches: Optional list of branches to track from the remote.
            timeout: Optional timeout for the operation.

        Raises:
            GitError: If adding the remote fails.
        """
        await self._check_is_git_repo(self.repo_path)

        cmd = ["remote", "add"]
        if track_branches:
            for branch in track_branches:
                cmd.extend(["-t", branch])
        cmd.extend([name, url])

        self._logger.info(
            "Adding remote '%s' with URL '%s' to %s...", name, url, self.repo_path
        )
        await self._run_git_cmd(cmd, cwd=self.repo_path, timeout=timeout)

    # Worktrees

    async def add_worktree(  # noqa: PLR0913
        self,
        path: str | Path,
        branch_or_commit: str,
        *,
        force: bool = False,
        detach: bool = False,
        checkout_options: Sequence[str] | None = None,
        timeout: int | None = None,
    ) -> Path:
        """Adds a new Git worktree.

        Corresponds to `git worktree add <path> <branch_or_commit>`.

        Args:
            path: The path where the new worktree will be created.
            branch_or_commit: The branch, commit hash, or tag to checkout in the
                new worktree.
            force: If `True`, creates the worktree even if the path exists and is
                not empty (uses `--force`).
            detach: If `True`, detach the HEAD of the new worktree (uses `--detach`).
            checkout_options: A list of additional options to pass to `git checkout`.
            timeout: Optional timeout for the operation.

        Returns:
            The absolute path to the newly created worktree.

        Raises:
            GitWorktreeCreationError: If the worktree creation fails.
        """
        await self._check_is_git_repo(self.repo_path)
        worktree_path = Path(path).resolve()

        cmd = ["worktree", "add"]
        if force:
            cmd.append("--force")
        if detach:
            cmd.append("--detach")
        if checkout_options:
            cmd.extend(checkout_options)

        cmd.extend([str(worktree_path), branch_or_commit])

        self._logger.info(
            "Adding new Git worktree at %s from %s...", worktree_path, branch_or_commit
        )
        try:
            _returncode, stdout, stderr = await self._run_git_cmd(
                cmd, cwd=self.repo_path, timeout=timeout
            )
        except GitError as exc:
            raise GitWorktreeCreationError(worktree_path) from exc

        if not worktree_path.is_dir() or not (worktree_path / ".git").exists():
            self._logger.error(
                "Failed to verify worktree creation at %s. Stdout: %s, Stderr: %s",
                worktree_path,
                stdout,
                stderr,
            )
            raise GitWorktreeCreationError(worktree_path)

        return worktree_path

    async def list_worktrees(
        self, timeout: int | None = None
    ) -> list[tuple[Path, str]]:
        """Lists existing Git worktrees.

        Corresponds to `git worktree list --porcelain`.

        Returns:
            A list of tuples, where each tuple contains:
                - Path: The absolute path to the worktree.
                - str: The HEAD commit or branch of the worktree.

        Raises:
            GitError: If listing worktrees fails.
        """
        await self._check_is_git_repo(self.repo_path)
        cmd = ["worktree", "list", "--porcelain"]

        self._logger.debug("Listing Git worktrees...")
        _returncode, stdout, _stderr = await self._run_git_cmd(
            cmd, cwd=self.repo_path, timeout=timeout
        )

        worktrees: list[tuple[Path, str]] = []
        current_worktree_path: Path | None = None
        current_head: str | None = None

        for line in stdout.splitlines():
            if line.startswith("worktree "):
                # Start of a new worktree entry
                if current_worktree_path and current_head:
                    worktrees.append((current_worktree_path, current_head))
                current_worktree_path = Path(line.split(" ", 1)[1]).resolve()
                current_head = None  # Reset head for the new worktree
            elif line.startswith("HEAD "):
                current_head = line.split(" ", 1)[1]
            elif line.startswith("branch "):
                # Extract branch name, e.g., "branch refs/heads/main" -> "main"
                # This prioritizes branch over bare HEAD if both are present in output
                branch_ref = line.split(" ", 1)[1]
                if branch_ref.startswith("refs/heads/"):
                    current_head = branch_ref.replace("refs/heads/", "")
                else:
                    current_head = branch_ref  # Fallback for other ref types

        # Add the last parsed worktree
        if current_worktree_path and current_head:
            worktrees.append((current_worktree_path, current_head))

        self._logger.debug("Found %d worktrees.", len(worktrees))
        return worktrees

    async def remove_worktree(
        self, path: str | Path, *, force: bool = False, timeout: int | None = None
    ) -> None:
        """Removes an existing Git worktree.

        Corresponds to `git worktree remove <path>`.

        Args:
            path: The path to the worktree to remove.
            force: If `True`, remove the worktree even if it has unstaged changes
                or uncommitted changes (uses `--force`).
            timeout: Optional timeout for the operation.

        Raises:
            GitError: If the worktree removal fails.
        """
        await self._check_is_git_repo(self.repo_path)
        worktree_path = Path(path).resolve()

        cmd = ["worktree", "remove"]
        if force:
            cmd.append("--force")
        cmd.append(str(worktree_path))

        self._logger.info("Removing Git worktree at %s...", worktree_path)
        await self._run_git_cmd(cmd, cwd=self.repo_path, timeout=timeout)

        if worktree_path.exists():
            self._logger.warning(
                "Worktree directory still exists after removal: %s", worktree_path
            )

    async def prune_worktrees(self, timeout: int | None = None) -> None:
        """Prunes stale Git worktree information.

        Corresponds to `git worktree prune`. This removes defunct worktree
        registrations from the main repository's `.git/worktrees` directory.

        Args:
            timeout: Optional timeout for the operation.

        Raises:
            GitError: If pruning fails.
        """
        await self._check_is_git_repo(self.repo_path)

        cmd = ["worktree", "prune"]

        self._logger.info("Pruning stale Git worktree entries...")
        await self._run_git_cmd(cmd, cwd=self.repo_path, timeout=timeout)

    async def move_worktree(
        self, old_path: str | Path, new_path: str | Path, timeout: int | None = None
    ) -> Path:
        """Moves an existing Git worktree to a new location.

        Corresponds to `git worktree move <old_path> <new_path>`.

        Args:
            old_path: The current path of the worktree.
            new_path: The new desired path for the worktree.
            timeout: Optional timeout for the operation.

        Returns:
            The absolute path to the newly moved worktree.

        Raises:
            GitWorktreeMissingPathError: If the `old_path` does not exist.
            GitWorktreeMoveError: If the worktree move operation fails.
        """
        await self._check_is_git_repo(self.repo_path)
        old_worktree_path = Path(old_path).resolve()
        new_worktree_path = Path(new_path).resolve()

        if not old_worktree_path.is_dir():
            raise GitWorktreeMissingPathError(old_worktree_path)

        cmd = ["worktree", "move", str(old_worktree_path), str(new_worktree_path)]

        self._logger.info(
            "Moving Git worktree from %s to %s...", old_worktree_path, new_worktree_path
        )
        try:
            await self._run_git_cmd(cmd, cwd=self.repo_path, timeout=timeout)
        except GitError as exc:
            raise GitWorktreeMoveError(old_worktree_path, new_worktree_path) from exc

        if not new_worktree_path.is_dir() or old_worktree_path.exists():
            self._logger.error(
                "Failed to verify worktree move from %s to %s.",
                old_worktree_path,
                new_worktree_path,
            )
            raise GitWorktreeMoveError(old_worktree_path, new_worktree_path)

        self._logger.info("Successfully moved worktree to %s", new_worktree_path)
        return new_worktree_path

    async def lock_worktree(
        self, path: str | Path, reason: str | None = None, timeout: int | None = None
    ) -> None:
        """Locks a Git worktree, preventing `git worktree prune` from removing it.

        Corresponds to `git worktree lock <path> [--reason <reason>]`.

        Args:
            path: The path to the worktree to lock.
            reason: An optional reason for locking the worktree.
            timeout: Optional timeout for the operation.

        Raises:
            GitError: If the worktree lock operation fails.
        """
        await self._check_is_git_repo(self.repo_path)
        worktree_path = Path(path).resolve()

        cmd = ["worktree", "lock", str(worktree_path)]
        if reason:
            cmd.extend(["--reason", reason])

        self._logger.info("Locking Git worktree at %s...", worktree_path)
        await self._run_git_cmd(cmd, cwd=self.repo_path, timeout=timeout)

    async def unlock_worktree(
        self, path: str | Path, timeout: int | None = None
    ) -> None:
        """Unlocks a Git worktree.

        Corresponds to `git worktree unlock <path>`.

        Args:
            path: The path to the worktree to unlock.
            timeout: Optional timeout for the operation.

        Raises:
            GitError: If the worktree unlock operation fails.
        """
        await self._check_is_git_repo(self.repo_path)
        worktree_path = Path(path).resolve()

        cmd = ["worktree", "unlock", str(worktree_path)]

        self._logger.info("Unlocking Git worktree at %s...", worktree_path)
        await self._run_git_cmd(cmd, cwd=self.repo_path, timeout=timeout)
