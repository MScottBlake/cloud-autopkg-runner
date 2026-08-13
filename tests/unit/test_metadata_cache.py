"""Tests for the metadata_cache module."""

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


def test_plugin_manager_singleton() -> None:
    """Test that PluginManager is a singleton."""
    plugin_manager1 = PluginManager()
    plugin_manager2 = PluginManager()
    assert plugin_manager1 is plugin_manager2


def test_plugin_manager_get_plugin() -> None:
    """Test that PluginManager returns the correct plugin."""
    plugin_manager = PluginManager()
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


@pytest.mark.parametrize(
    ("plugin_name", "expected_type", "extra_settings"),
    [
        ("default", AsyncJsonFileCache, {}),
        ("json", AsyncJsonFileCache, {}),
        ("sqlite", AsyncSQLiteCache, {"cache_file": "cache_file.sqlite"}),
        ("s3", AsyncS3Cache, {"cloud_container_name": "fake_bucket"}),
        ("gcs", AsyncGCSCache, {"cloud_container_name": "fake_bucket"}),
        (
            "azure",
            AsyncAzureBlobCache,
            {
                "cloud_container_name": "fake_bucket",
                "azure_account_url": "https://fake_account_url",
            },
        ),
    ],
    ids=["default", "json", "sqlite", "s3", "gcs", "azure"],
)
def test_plugin_manager_load_plugin(
    plugin_name: str,
    expected_type: type[MetadataCachePlugin],
    extra_settings: dict[str, str],
) -> None:
    """Test that each entry point resolves to its backend."""
    plugin_manager = PluginManager()

    settings = Settings()
    settings.cache_plugin = plugin_name
    settings.cache_file = "cache_file.json"
    for name, value in extra_settings.items():
        setattr(settings, name, value)

    plugin_manager.load_plugin()

    assert isinstance(plugin_manager.plugin, expected_type)
    assert isinstance(plugin_manager.plugin, MetadataCachePlugin)


def test_plugin_manager_load_plugin_error_handling() -> None:
    """Test that PluginManager handles plugin loading errors correctly."""
    plugin_manager = PluginManager()
    settings = Settings()
    settings.cache_plugin = "nonexistent"

    with pytest.raises(PluginManagerEntryPointError):
        plugin_manager.load_plugin()
