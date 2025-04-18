"""Provides common utility functions for cloud-autopkg-runner.

This module encapsulates general-purpose utility functions that are
used throughout the cloud-autopkg-runner project.  Currently, it includes
a function for generating a list of possible AutoPkg recipe file names
based on common naming conventions.

Functions:
    list_possible_file_names: Generates a list of possible AutoPkg recipe
        file names for a given recipe name.
"""


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
