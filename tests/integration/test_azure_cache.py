import json
from datetime import datetime, timezone

import pytest
from azure.storage.blob.aio import BlobServiceClient

from cloud_autopkg_runner import Settings
from cloud_autopkg_runner.cache.azure_blob_cache import AsyncAzureBlobCache
from cloud_autopkg_runner.metadata_cache import MetadataCachePlugin, RecipeCache

# Define test data outside of a class
TEST_RECIPE_NAME = "test.pkg.recipe"
TEST_TIMESTAMP_STR = datetime(2023, 10, 26, 10, 30, 0, tzinfo=timezone.utc).isoformat()


@pytest.mark.asyncio
async def test_save_and_read_azure_cache_file(
    azure_blob_service_client: BlobServiceClient,
    azure_test_container: str,
    azure_cache_plugin: MetadataCachePlugin,
) -> None:
    """Test writing a cache file to Azure Blob Storage and then reading it back."""
    test_data: RecipeCache = {
        "timestamp": TEST_TIMESTAMP_STR,
        "metadata": [
            {
                "file_path": "/tmp/azure-test-app-1.0.exe",
                "file_size": 54321,
                "etag": "fedcba98765",
                "last_modified": TEST_TIMESTAMP_STR,
            }
        ],
    }

    current_settings = Settings()
    blob_name = current_settings.cache_file

    await azure_cache_plugin.set_item(TEST_RECIPE_NAME, test_data)
    await azure_cache_plugin.save()

    # Retrieve data with a new plugin (no stored data)
    async with AsyncAzureBlobCache() as new_plugin:
        loaded_data = await new_plugin.get_item(TEST_RECIPE_NAME)
        assert loaded_data == test_data

    # Retrieve full file with azure client
    container_client = azure_blob_service_client.get_container_client(
        azure_test_container
    )
    blob_client = container_client.get_blob_client(blob_name)

    # Download the blob content
    download_stream = await blob_client.download_blob()
    content = await download_stream.readall()

    actual_azure_content = json.loads(content.decode("utf-8"))

    # The cache structure is {RecipeName: RecipeCache}
    expected_azure_content_dict = {TEST_RECIPE_NAME: test_data}
    assert actual_azure_content == expected_azure_content_dict
