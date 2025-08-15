"""Tests for the metadata_cache module."""

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from cloud_autopkg_runner import Settings
from cloud_autopkg_runner.cache.azure_blob_cache import AsyncAzureBlobCache
from cloud_autopkg_runner.cache.gcs_cache import AsyncGCSCache
from cloud_autopkg_runner.cache.json_cache import AsyncJsonFileCache
from cloud_autopkg_runner.cache.s3_cache import AsyncS3Cache
from cloud_autopkg_runner.cache.sqlite_cache import AsyncSQLiteCache
from cloud_autopkg_runner.exceptions import PluginManagerEntryPointError
from cloud_autopkg_runner.metadata_cache import (
    MetadataCachePlugin,
    PluginManager,
    get_cache_plugin,
)


@pytest.fixture
def plugin_manager() -> Generator[PluginManager, Any, None]:
    """Fixture that yields PluginManager and removes _instance after."""
    with (
        patch.object(Settings, "_instance", None),
        patch.object(PluginManager, "_instance", None),
    ):
        yield PluginManager()


def test_plugin_manager_singleton() -> None:
    """Test that PluginManager is a singleton."""
    plugin_manager1 = PluginManager()
    plugin_manager2 = PluginManager()
    assert plugin_manager1 is plugin_manager2


def test_plugin_manager_get_plugin(plugin_manager: PluginManager) -> None:
    """Test that PluginManager returns the correct plugin."""
    plugin_manager.plugin = MagicMock()
    assert plugin_manager.get_plugin() == plugin_manager.plugin


def test_get_cache_plugin() -> None:
    """Test that get_cache_plugin returns the correct plugin."""
    with patch(
        "cloud_autopkg_runner.metadata_cache.PluginManager.get_plugin",
        return_value=MagicMock(),
    ) as mock_get_plugin:
        plugin = get_cache_plugin()
        assert plugin == mock_get_plugin.return_value
        mock_get_plugin.assert_called_once()


def test_plugin_manager_load_plugin_default(plugin_manager: PluginManager) -> None:
    """Test successful plugin loading."""
    settings = Settings()
    settings.cache_plugin = "default"
    settings.cache_file = "cache_file.json"

    plugin_manager.load_plugin()

    assert isinstance(plugin_manager.plugin, AsyncJsonFileCache)
    assert isinstance(plugin_manager.plugin, MetadataCachePlugin)


def test_plugin_manager_load_plugin_json(plugin_manager: PluginManager) -> None:
    """Test successful plugin loading."""
    settings = Settings()
    settings.cache_plugin = "json"
    settings.cache_file = "cache_file.json"

    plugin_manager.load_plugin()

    assert isinstance(plugin_manager.plugin, AsyncJsonFileCache)
    assert isinstance(plugin_manager.plugin, MetadataCachePlugin)


def test_plugin_manager_load_plugin_azure(plugin_manager: PluginManager) -> None:
    """Test successful plugin loading."""
    settings = Settings()
    settings.cache_plugin = "azure"
    settings.cache_file = "cache_file.json"
    settings.cloud_container_name = "fake_bucket"
    settings.azure_account_url = "https://fake_account_url"

    plugin_manager.load_plugin()

    assert isinstance(plugin_manager.plugin, AsyncAzureBlobCache)
    assert isinstance(plugin_manager.plugin, MetadataCachePlugin)


def test_plugin_manager_load_plugin_gcs(plugin_manager: PluginManager) -> None:
    """Test successful plugin loading."""
    settings = Settings()
    settings.cache_plugin = "gcs"
    settings.cache_file = "cache_file.json"
    settings.cloud_container_name = "fake_bucket"

    plugin_manager.load_plugin()

    assert isinstance(plugin_manager.plugin, AsyncGCSCache)
    assert isinstance(plugin_manager.plugin, MetadataCachePlugin)


def test_plugin_manager_load_plugin_s3(plugin_manager: PluginManager) -> None:
    """Test successful plugin loading."""
    settings = Settings()
    settings.cache_plugin = "s3"
    settings.cache_file = "cache_file.json"
    settings.cloud_container_name = "fake_bucket"

    plugin_manager.load_plugin()

    assert isinstance(plugin_manager.plugin, AsyncS3Cache)
    assert isinstance(plugin_manager.plugin, MetadataCachePlugin)


def test_plugin_manager_load_plugin_sqlite(plugin_manager: PluginManager) -> None:
    """Test successful plugin loading."""
    settings = Settings()
    settings.cache_plugin = "sqlite"
    settings.cache_file = "cache_file.sqlite"

    plugin_manager.load_plugin()

    assert isinstance(plugin_manager.plugin, AsyncSQLiteCache)
    assert isinstance(plugin_manager.plugin, MetadataCachePlugin)


def test_plugin_manager_load_plugin_error_handling(
    plugin_manager: PluginManager,
) -> None:
    """Test that PluginManager handles plugin loading errors correctly."""
    settings = Settings()
    settings.cache_plugin = "nonexistent"

    with pytest.raises(PluginManagerEntryPointError):
        plugin_manager.load_plugin()
