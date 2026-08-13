"""Tests that singleton state does not leak between tests.

Every test in this module deliberately builds singleton state that would be
visible to the tests that follow it. They pass in isolation whether or not the
autouse reset in conftest is in place; they only fail as a group, and only
when that reset is missing. Run the module as a whole to exercise it.
"""

import json
from pathlib import Path

import pytest

from cloud_autopkg_runner import Settings
from cloud_autopkg_runner.cache.json_cache import AsyncJsonFileCache
from cloud_autopkg_runner.metadata_cache import PluginManager, get_cache_plugin


def _write_cache(cache_file: Path, recipe_name: str) -> None:
    """Write a single-entry metadata cache to disk.

    Args:
        cache_file: Where to write the cache.
        recipe_name: The recipe name to record in it.
    """
    cache_file.write_text(
        json.dumps({recipe_name: {"timestamp": "foo", "metadata": []}})
    )


@pytest.mark.asyncio
async def test_cache_plugin_reads_first_configured_file(tmp_path: Path) -> None:
    """Load a cache so a later test would inherit it without isolation."""
    cache_file = tmp_path / "first.json"
    _write_cache(cache_file, "FirstRecipe")

    settings = Settings()
    settings.cache_file = str(cache_file)

    assert await get_cache_plugin().load() == {
        "FirstRecipe": {"timestamp": "foo", "metadata": []}
    }


@pytest.mark.asyncio
async def test_cache_plugin_reads_second_configured_file(tmp_path: Path) -> None:
    """A different cache file must be honored, not the previous test's."""
    cache_file = tmp_path / "second.json"
    _write_cache(cache_file, "SecondRecipe")

    settings = Settings()
    settings.cache_file = str(cache_file)

    assert await get_cache_plugin().load() == {
        "SecondRecipe": {"timestamp": "foo", "metadata": []}
    }


def test_settings_starts_from_defaults() -> None:
    """Settings must not carry values assigned by an earlier test."""
    assert Settings().cache_file == "metadata_cache.json"
    assert Settings().max_concurrency == 10

    Settings().cache_file = "mutated.json"
    Settings().max_concurrency = 99


def test_settings_defaults_survive_previous_mutation() -> None:
    """The mutations made by the previous test must not be visible here."""
    assert Settings().cache_file == "metadata_cache.json"
    assert Settings().max_concurrency == 10


def test_plugin_manager_starts_unresolved() -> None:
    """PluginManager must not reuse a plugin resolved by an earlier test."""
    Settings().cache_plugin = "sqlite"
    manager = PluginManager()

    assert type(manager.get_plugin()).__name__ == "AsyncSQLiteCache"


def test_plugin_manager_resolves_the_current_plugin() -> None:
    """A later test choosing a different backend must actually get it."""
    Settings().cache_plugin = "json"
    manager = PluginManager()

    assert isinstance(manager.get_plugin(), AsyncJsonFileCache)
