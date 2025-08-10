"""Defines custom exception classes for the cloud-autopkg-runner package.

These exceptions are used to provide more specific error handling and
reporting within the application. They inherit from the `BaseException`
class.
"""

from pathlib import Path


class AutoPkgRunnerException(BaseException):
    """Base exception class for the AutoPkg runner."""


# Cache
class PluginManagerError(AutoPkgRunnerException):
    """Base exception class for handling invalid cache plugins."""

    def __init__(self, plugin_name: str) -> None:
        """Initializes PluginManagerError with the name of a plugin.

        Args:
            plugin_name: The name of a cache plugin.
        """
        super().__init__(f"Failed to load '{plugin_name}' metadata cache plugin.")


class PluginManagerEntryPointError(PluginManagerError):
    """Exception class for handling invalid cache plugins missing entry points."""

    def __init__(self, plugin_name: str) -> None:
        """Initializes PluginManagerEntryPointError with the name of a plugin.

        Args:
            plugin_name: The name of a cache plugin.
        """
        super().__init__(f"No entry point found for cache plugin: {plugin_name}")


class InvalidCacheContents(AutoPkgRunnerException):
    """Base exception class for handling invalid cache contents.

    This exception is raised when a cache is found to contain invalid data
    or is improperly formatted.
    """

    def __init__(self) -> None:
        """Initializes InvalidCacheContents with the path to the invalid file."""
        super().__init__("Invalid cache contents.")


# File Contents
class InvalidFileContents(AutoPkgRunnerException):
    """Base exception class for handling invalid file contents.

    This exception is raised when a file is found to contain invalid data
    or is improperly formatted.
    """

    def __init__(self, file_path: Path) -> None:
        """Initializes InvalidFileContents with the path to the invalid file.

        Args:
            file_path: The path to the file with invalid contents.
        """
        super().__init__(f"Invalid file contents in {file_path}")


class InvalidJsonContents(InvalidFileContents):
    """Exception class for handling invalid JSON file contents.

    This exception is raised when a JSON file is found to contain invalid JSON
    data that cannot be parsed.
    """


class InvalidPlistContents(InvalidFileContents):
    """Exception class for handling invalid plist file contents.

    This exception is raised when a plist (Property List) file is found to
    contain invalid data that cannot be parsed.
    """


class InvalidYamlContents(InvalidFileContents):
    """Exception class for handling invalid YAML file contents.

    This exception is raised when a YAML file is found to contain invalid YAML
    data that cannot be parsed.
    """


# AutoPkgPrefs
class PreferenceFileNotFoundError(AutoPkgRunnerException):
    """Raised when the AutoPkg preferences file is not found.

    This exception indicates that the specified AutoPkg preferences file
    does not exist at the expected location.
    """

    def __init__(self, file_path: Path) -> None:
        """Initializes PreferenceFileNotFoundError with the missing file path.

        Args:
            file_path: The path to the preferences file that was not found.
        """
        super().__init__(f"Plist file not found: {file_path}")


class PreferenceKeyNotFoundError(AutoPkgRunnerException):
    """Raised when a requested preference key is missing.

    This exception indicates that the requested preference key does not
    exist in the loaded AutoPkg preferences.
    """

    def __init__(self, attribute: str) -> None:
        """Initializes PreferenceKeyNotFoundError with the missing attribute name.

        Args:
            attribute: The name of the attribute that was not found.
        """
        super().__init__(f"AutoPkgPrefs has no attribute '{attribute}'")


# Recipe
class RecipeException(AutoPkgRunnerException):
    """Base exception class for handling recipe issues.

    This exception serves as a base class for more specific exceptions
    related to AutoPkg recipe processing.
    """


class RecipeInputException(RecipeException):
    """Exception class for handling issues related to recipe input values.

    This exception is raised when there is a problem with the input values
    defined in an AutoPkg recipe, such as a missing or invalid required input.
    """

    def __init__(self, file_path: Path) -> None:
        """Initializes RecipeInputException with the path to the affected recipe.

        Args:
            file_path: The path to the recipe file with the input issue.
        """
        super().__init__(f"Invalid or missing input value in {file_path} contents.")


class RecipeLookupException(RecipeException):
    """Exception class for handling issues finding a recipe by name.

    This exception is raised when a recipe cannot be found using the specified
    recipe name. This may indicate that the recipe does not exist or is not
    in the search path.
    """

    def __init__(self, recipe_name: str) -> None:
        """Initializes RecipeLookupException with the name of the unfound recipe.

        Args:
            recipe_name: The name of the recipe that could not be found.
        """
        super().__init__(f"No recipe found matching {recipe_name}")


class RecipeFormatException(RecipeException):
    """Exception class for handling unknown recipe formats.

    This exception is raised when a recipe file has an unrecognized or
    unsupported file extension.
    """

    def __init__(self, recipe_extension: str) -> None:
        """Initializes RecipeFormatException with the invalid file extension.

        Args:
            recipe_extension: The file extension of the invalid recipe file.
        """
        super().__init__(f"Invalid recipe format: {recipe_extension}")


# Settings
class SettingsValidationError(AutoPkgRunnerException):
    """Exception class for handling validation errors in Settings.

    This exception is raised when a Setting value does not validate successfully.
    """

    def __init__(self, field_name: str, validation_error: str) -> None:
        """Initializes SettingsValidationError with the invalid file extension.

        Args:
            field_name: The name of the invalid Setting.
            validation_error: The message explaining the failure.
        """
        super().__init__(f"Invalid value for '{field_name}': {validation_error}")


# Shell Command
class ShellCommandException(AutoPkgRunnerException):
    """Base exception class for handling issues with shell commands.

    This exception serves as a base class for more specific exceptions
    related to shell command execution.
    """


# Git
class GitError(AutoPkgRunnerException):
    """Base exception for all Git-related errors.

    This class serves as a parent for more specific exceptions that
    can occur during Git operations.
    """


class GitRepoDoesNotExistError(GitError):
    """Exception raised when a specified Git repository path does not exist.

    This indicates that the directory provided as a repository path
    does not exist on the file system.
    """

    def __init__(self, path: Path) -> None:
        """Initializes GitRepoDoesNotExistError.

        Args:
            path: The path that was expected to be a Git repository
                but does not exist.
        """
        super().__init__(f"Repository path does not exist: {path}")


class PathNotGitRepoError(GitError):
    """Exception raised when a specified path is not a Git repository.

    This indicates that the directory exists, but it does not contain
    the necessary Git repository structure (e.g., a `.git` directory).
    """

    def __init__(self, path: Path) -> None:
        """Initializes PathNotGitRepoError.

        Args:
            path: The path that was expected to be a Git repository
                but lacks the Git repository structure.
        """
        super().__init__(f"Path does not appear to be a Git repository: {path}")


class GitDefaultBranchError(GitError):
    """Exception raised when the default branch for a remote cannot be determined.

    This can occur if the remote does not exist, or its `HEAD` reference is not
    clearly defined in `git remote show` output.
    """

    def __init__(self, remote_name: str) -> None:
        """Initializes GitDefaultBranchError.

        Args:
            remote_name: The name of the remote for which the default branch
                         could not be determined.
        """
        super().__init__(
            f"Could not determine default branch for remote '{remote_name}'."
        )


class GitMergeError(GitError):
    """Exception raised when a Git merge operation fails.

    This typically indicates a conflict, or that the target branch was not
    currently checked out when the merge was attempted.
    """

    def __init__(self, target_branch: str, current_branch: str) -> None:
        """Initializes GitMergeError.

        Args:
            target_branch: The branch that was intended to be the merge target.
            current_branch: The branch that was actually checked out when the merge was
                attempted.
        """
        super().__init__(
            f"Cannot merge: '{target_branch}' is not currently checked out. "
            f"Current branch is '{current_branch}'."
        )


class GitWorktreeError(GitError):
    """Base exception for errors specific to Git worktree operations.

    This exception is raised when a generic failure occurs during
    a `git worktree` command execution.
    """

    def __init__(self, cmd_str: str) -> None:
        """Initializes GitWorktreeError.

        Args:
            cmd_str: The string representation of the Git command that failed.
        """
        super().__init__(f"Git worktree command failed: '{cmd_str}'")


class GitWorktreeCreationError(GitWorktreeError):
    """Exception raised when a Git worktree fails to be created.

    This indicates that the `git worktree add` command did not result
    in a valid new worktree at the specified path.
    """

    def __init__(self, path: Path) -> None:
        """Initializes GitWorktreeCreationError.

        Args:
            path: The intended path for the new worktree where creation failed.
        """
        super().__init__(f"Failed to create worktree at {path}")


class GitWorktreeMissingPathError(GitWorktreeError):
    """Exception raised when a specified worktree path does not exist.

    This is typically used when attempting to operate on an existing worktree
    (e.g., `remove`, `move`, `lock`, `unlock`) and the path provided
    does not point to an existing directory.
    """

    def __init__(self, path: Path) -> None:
        """Initializes GitWorktreeMissingPathError.

        Args:
            path: The path that was expected to point to an existing worktree
                but does not exist.
        """
        super().__init__(f"Worktree directory does not exist: {path}")


class GitWorktreeMoveError(GitWorktreeError):
    """Exception raised when a Git worktree fails to be moved.

    This indicates that the `git worktree move` command did not
    successfully relocate the worktree from its old path to the new one.
    """

    def __init__(self, old_path: Path, new_path: Path) -> None:
        """Initializes GitWorktreeMoveError.

        Args:
            old_path: The original path of the worktree.
            new_path: The intended new path for the worktree.
        """
        super().__init__(f"Failed to move worktree from {old_path} to {new_path}")
