import asyncio
import importlib
from collections.abc import Generator

import pytest

from cloud_autopkg_runner import Settings
from cloud_autopkg_runner.metadata_cache import PluginManager

# Cache backends live behind optional extras, so they are resolved by name and
# skipped when the extra is not installed.
_CACHE_SINGLETONS: tuple[tuple[str, str], ...] = (
    ("cloud_autopkg_runner.cache.json_cache", "AsyncJsonFileCache"),
    ("cloud_autopkg_runner.cache.sqlite_cache", "AsyncSQLiteCache"),
    ("cloud_autopkg_runner.cache.s3_cache", "AsyncS3Cache"),
    ("cloud_autopkg_runner.cache.gcs_cache", "AsyncGCSCache"),
    ("cloud_autopkg_runner.cache.azure_blob_cache", "AsyncAzureBlobCache"),
)


def singleton_classes() -> list[type]:
    """Collect every singleton class that leaks state between tests.

    Returns:
        The singleton classes available in this environment.
    """
    classes: list[type] = [Settings, PluginManager]

    for module_name, class_name in _CACHE_SINGLETONS:
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        classes.append(getattr(module, class_name))

    return classes


def _reset_singletons() -> None:
    """Discard every cached singleton instance and its class-level lock."""
    for cls in singleton_classes():
        cls._instance = None

        # Locks bind to the first event loop that contends for them, which
        # would outlive the per-test loop.
        if isinstance(getattr(cls, "_lock", None), asyncio.Lock):
            cls._lock = asyncio.Lock()


@pytest.fixture(autouse=True)
def reset_singletons() -> Generator[None, None, None]:
    """Fixture to reset the singleton instances around each test.

    Applies to the unit and integration suites alike.

    Settings, PluginManager, and every cache backend cache their first
    instance for the lifetime of the process. Each cache backend also latches
    onto the container and cache file it was constructed with, along with the
    data it has already loaded, so without this the first test to touch the
    cache pins all of that for every test that follows.

    Resetting before as well as after keeps a test from inheriting state built
    during collection or left behind by a test that errored.

    Yields:
        None.
    """
    _reset_singletons()
    yield
    _reset_singletons()
