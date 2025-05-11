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

from .settings import Settings  # noqa: I001

from .autopkg_prefs import AutoPkgPrefs
from .metadata_cache import get_cache_plugin
from .recipe import Recipe
from .recipe_finder import RecipeFinder
from .recipe_report import RecipeReport

__all__ = [
    "AutoPkgPrefs",
    "Recipe",
    "RecipeFinder",
    "RecipeReport",
    "Settings",
    "get_cache_plugin",
]
