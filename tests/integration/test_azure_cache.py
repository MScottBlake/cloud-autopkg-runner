import contextlib
import json
import os
import time
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.identity.aio import DefaultAzureCredential
from azure.storage.blob.aio import BlobClient, BlobServiceClient

from cloud_autopkg_runner import Settings
from cloud_autopkg_runner.metadata_cache import RecipeCache, get_cache_plugin

# Define test data outside of a class
TEST_RECIPE_NAME = "test.pkg.recipe"
TEST_TIMESTAMP_STR = datetime(2023, 10, 26, 10, 30, 0, tzinfo=timezone.utc).isoformat()


# Fixtures


def generate_unique_name(prefix: str) -> str:
    """Generates a unique, compliant container name."""
    unique_part = uuid.uuid4().hex[:8]
    timestamp_part = str(int(time.time()))
    sanitized_prefix = prefix.lower().replace("_", "-").replace(".", "-")
    full_name = f"{sanitized_prefix}-{unique_part}-{timestamp_part}"
    return full_name[:63].strip("-")


@pytest.fixture
def settings() -> Settings:
    """Setup the Settings class."""
    settings = Settings()
    settings.cache_plugin = "azure"
    settings.cloud_container_name = generate_unique_name("cloud-autopkg-test-azure")
    settings.cache_file = "metadata_cache.json"
    settings.azure_account_url = os.environ.get(
        "AZURE_ACCOUNT_URL", "https://127.0.0.1:10000/devstoreaccount1"
    )

    yield settings

    Settings._instance = None


@pytest.fixture
def test_data() -> RecipeCache:
    """Provides a standard set of test data."""
    return {
        "timestamp": TEST_TIMESTAMP_STR,
        "metadata": [
            {
                "file_path": "/tmp/azure-test-app-1.0.pkg",
                "file_size": 54321,
                "etag": "fedcba98765",
                "last_modified": TEST_TIMESTAMP_STR,
            }
        ],
    }


@pytest_asyncio.fixture
async def azure_blob_client(settings: Settings) -> AsyncGenerator[BlobClient, None]:
    """Fixture that provides a valid BlobClient."""
    async with (
        DefaultAzureCredential() as credential,
        BlobServiceClient(
            account_url=settings.azure_account_url, credential=credential
        ) as azure_blob_service_client,
        azure_blob_service_client.get_blob_client(
            container=settings.cloud_container_name, blob=settings.cache_file
        ) as blob_client,
    ):
        with contextlib.suppress(ResourceExistsError):
            await azure_blob_service_client.create_container(
                name=settings.cloud_container_name
            )

        yield blob_client

        with contextlib.suppress(ResourceNotFoundError):
            await blob_client.delete_blob(delete_snapshots="include")
            await azure_blob_service_client.delete_container(
                container=settings.cloud_container_name
            )


# Tests


@pytest.mark.asyncio
async def test_save_cache_file(
    azure_blob_client: BlobClient, test_data: RecipeCache
) -> None:
    """Test writing a cache file to Azure Blob Storage."""
    # Store with plugin
    plugin = get_cache_plugin()
    async with plugin:
        await plugin.set_item(TEST_RECIPE_NAME, test_data)
        await plugin.save()

    expected_content = {TEST_RECIPE_NAME: test_data}

    # Retrieve with standard tooling
    download_stream = await azure_blob_client.download_blob()
    content = await download_stream.readall()
    actual_content = json.loads(content.decode("utf-8"))

    assert actual_content == expected_content


@pytest.mark.asyncio
async def test_retrieve_cache_file(
    azure_blob_client: BlobClient, test_data: RecipeCache
) -> None:
    """Test retrieving a cache file from Azure Blob Storage."""
    # Store with standard tooling
    content = json.dumps({TEST_RECIPE_NAME: test_data})
    await azure_blob_client.upload_blob(data=content.encode("utf-8"), overwrite=True)

    # Retrieve with plugin
    plugin = get_cache_plugin()
    async with plugin:
        actual_content = await plugin.get_item(TEST_RECIPE_NAME)

    assert actual_content == test_data
