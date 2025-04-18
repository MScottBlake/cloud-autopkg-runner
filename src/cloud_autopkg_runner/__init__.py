"""The cloud-autopkg-runner package.

This package provides asynchronous tools and utilities for managing
AutoPkg recipes and workflows. It includes modules for handling
metadata caching, recipe processing, shell command execution, and
more.

Key features include:
- Asynchronous execution of AutoPkg recipes for improved performance.
- Robust error handling and logging.
- Integration with AutoPkg's preference system.
- Flexible command-line interface for specifying recipes and options.
- Metadata caching to reduce redundant downloads.
"""

from .settings import settings

__all__ = [
    "settings",
]


# Located here to prevent circular imports
def list_possible_file_names(recipe_name: str) -> list[str]:
    """Generate a list of possible AutoPkg recipe file names.

    Given a recipe name, this function returns a list of possible file names
    by appending common AutoPkg recipe file extensions. If the recipe name
    already ends with a known extension, it returns a list containing only the
    original recipe name.

    Args:
        recipe_name: The name of the AutoPkg recipe.

    Returns:
        A list of possible file names for the recipe.
    """
    if recipe_name.endswith((".recipe", ".recipe.plist", ".recipe.yaml")):
        return [recipe_name]

    return [
        recipe_name + ".recipe",
        recipe_name + ".recipe.plist",
        recipe_name + ".recipe.yaml",
    ]
