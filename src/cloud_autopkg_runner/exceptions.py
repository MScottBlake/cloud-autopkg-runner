"""Defines custom exception classes for the cloud-autopkg-runner package.

These exceptions are used to provide more specific error handling and
reporting within the application. They inherit from the `BaseException`
class.
"""

from pathlib import Path


class AutoPkgRunnerException(BaseException):
    """Base exception class for the AutoPkg runner."""


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


# Shell Command
class ShellCommandException(AutoPkgRunnerException):
    """Base exception class for handling issues with shell commands.

    This exception serves as a base class for more specific exceptions
    related to shell command execution.
    """
