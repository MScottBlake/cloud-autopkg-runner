import json
import os
import time
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from azure.identity.aio import DefaultAzureCredential
from azure.storage.blob import StorageErrorCode
from azure.storage.blob.aio import BlobServiceClient

from cloud_autopkg_runner import Settings
from cloud_autopkg_runner.cache.azure_blob_cache import AsyncAzureBlobCache
from cloud_autopkg_runner.metadata_cache import (
    MetadataCachePlugin,
    RecipeCache,
    get_cache_plugin,
)

# Define test data outside of a class
TEST_RECIPE_NAME = "test.pkg.recipe"
TEST_TIMESTAMP_STR = datetime(2023, 10, 26, 10, 30, 0, tzinfo=timezone.utc).isoformat()


# Fixtures


def generate_unique_name(prefix: str) -> str:
    """Generates a unique name for cloud resources, sanitized for S3 bucket names."""
    # Container names can be between 3 and 63 characters long.
    # Container names must start with a letter or number, and can contain only lowercase
    # letters, numbers, and the dash (-) character.
    # Consecutive dash characters aren't permitted in container names.
    unique_part = uuid.uuid4().hex[:8]
    timestamp_part = str(int(time.time()))
    sanitized_prefix = prefix.lower().replace("_", "-").replace(".", "-")
    full_name = f"{sanitized_prefix}-{unique_part}-{timestamp_part}"
    return full_name[:63].strip("-")


@pytest_asyncio.fixture(scope="session")
async def azure_blob_service_client() -> AsyncGenerator[BlobServiceClient, None]:
    """Provides a low-level Azure Blob Service Client for session-scoped operations.

    This client is configured to connect to Azurite using its default connection string.
    """
    host = os.environ.get("AZURE_STORAGE_HOST", "127.0.0.1:10000")
    account = os.environ.get("AZURE_STORAGE_ACCOUNT")
    url = f"https://{host}/{account}"

    async with BlobServiceClient(url, DefaultAzureCredential()) as client:
        # async with BlobServiceClient(
        #     url, DefaultAzureCredential(), connection_verify=False
        # ) as client:
        yield client


@pytest_asyncio.fixture
async def azure_test_container(
    azure_blob_service_client: BlobServiceClient,
) -> AsyncGenerator[str, None]:
    """Creates a temporary Azure Blob Storage container and cleans up after use.

    This async generator yields the name of a uniquely generated Azure container,
    then deletes all blobs within it and removes the container upon completion.
    """
    container_name = generate_unique_name("cloud-autopkg-test-azure")
    print(f"Creating Azure container: {container_name}")
    container_client = azure_blob_service_client.get_container_client(container_name)
    container_client.create_container()

    yield container_name

    print(f"Cleaning up Azure container: {container_name}")

    # List and delete all blobs
    # container_client = azure_blob_service_client.get_container_client(
    #     container_name
    # )
    async for blob_item in container_client.list_blobs():
        try:
            await container_client.delete_blob(blob_item.name)
        except Exception as e:  # noqa: BLE001
            print(f"Warning: Failed to delete blob {blob_item.name}: {e}")

    # Delete the container itself
    try:
        await azure_blob_service_client.delete_container(container_name)
    except Exception as e:
        # Handle cases where container might not exist or be empty during cleanup
        if not isinstance(e, type(StorageErrorCode.CONTAINER_NOT_FOUND)):
            print(f"Error during container cleanup {container_name}: {e}")
            raise


@pytest_asyncio.fixture
async def azure_cache_plugin(
    azure_test_container: str,
) -> AsyncGenerator[MetadataCachePlugin, None]:
    """Provides an initialized AsyncAzureBlobCache plugin pointing to a test container.

    This fixture configures the Settings object for the test run to ensure the
    AsyncAzureBlobCache is instantiated and uses the temporary test container.
    """
    settings = Settings()
    settings.cache_plugin = "azure"
    settings.cloud_container_name = azure_test_container
    settings.cache_file = "metadata_cache.json"
    settings.azure_account_url = "https://127.0.0.1:10000/devstoreaccount1"

    # get_cache_plugin() should return AsyncAzureBlobCache due to settings.cache_plugin
    plugin = get_cache_plugin()
    # plugin = AsyncAzureBlobCache()
    await plugin.open()
    await plugin.clear_cache()
    yield plugin
    await plugin.close()


# Tests


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
