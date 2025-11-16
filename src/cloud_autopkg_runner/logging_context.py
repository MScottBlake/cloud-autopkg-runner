"""Provides a context variable for logging recipe-specific information.

This module defines a ContextVar that stores the currently executing
recipe name. Logging filters can read this variable to automatically
tag log messages with the correct recipe context, even in concurrent
async execution.

Usage:
    from cloud_autopkg_runner.logging_context import recipe_context
    recipe_context.set("MyRecipe.pkg.recipe")
"""

import contextvars

recipe_context = contextvars.ContextVar("recipe", default=__package__)
