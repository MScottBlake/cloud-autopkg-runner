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
from .config_loader import ConfigLoader
from .config_schema import ConfigSchema
from .git_client import GitClient
from .metadata_cache import get_cache_plugin
from .recipe import Recipe
from .recipe_finder import RecipeFinder
from .recipe_report import RecipeReport
from . import logging_config

__all__ = [
    "AutoPkgPrefs",
    "ConfigLoader",
    "ConfigSchema",
    "GitClient",
    "Recipe",
    "RecipeFinder",
    "RecipeReport",
    "Settings",
    "get_cache_plugin",
]

# Library-level logger
logger = logging_config.get_logger(__name__)
