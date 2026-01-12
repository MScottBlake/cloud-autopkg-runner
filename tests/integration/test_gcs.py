import asyncio
import json
import time
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from google.cloud.storage import Client

from cloud_autopkg_runner import Settings
from cloud_autopkg_runner.metadata_cache import RecipeCache, get_cache_plugin

TEST_RECIPE_NAME = "test.pkg.recipe"
TEST_TIMESTAMP_STR = datetime(2023, 10, 26, 10, 30, 0, tzinfo=timezone.utc).isoformat()

# Fixtures


def generate_unique_name(prefix: str) -> str:
    """Generates a unique, compliant bucket name."""
    unique_part = uuid.uuid4().hex[:8]
    timestamp_part = str(int(time.time()))
    sanitized_prefix = prefix.lower().replace("_", "-").replace(".", "-")
    full_name = f"{sanitized_prefix}-{unique_part}-{timestamp_part}"
    return full_name[:63].strip("-")


@pytest.fixture
def settings() -> Settings:
    """Setup the Settings class."""
    settings = Settings()
    settings.cache_plugin = "gcs"
    settings.cloud_container_name = generate_unique_name("cloud-autopkg-test-gcs")
    settings.cache_file = "metadata_cache.json"

    yield settings

    Settings._instance = None


@pytest.fixture
def test_data() -> RecipeCache:
    """Provides a standard set of test data."""
    return {
        "timestamp": TEST_TIMESTAMP_STR,
        "metadata": [
            {
                "file_path": "/tmp/gcs-test-app-1.0.pkg",
                "file_size": 54321,
                "etag": "fedcba98765",
                "last_modified": TEST_TIMESTAMP_STR,
            }
        ],
    }


@pytest_asyncio.fixture
async def gcs_client(settings: Settings) -> AsyncGenerator[Client, None]:
    """Provide a GCS client wrapped for async use."""
    client = await asyncio.to_thread(Client)
    bucket_name = settings.cloud_container_name

    bucket = await asyncio.to_thread(client.create_bucket, bucket_name)

    yield client

    blob = bucket.blob(settings.cache_file)
    await asyncio.to_thread(blob.delete)
    await asyncio.to_thread(bucket.delete)


# Tests


@pytest.mark.asyncio
async def test_save_cache_file(
    gcs_client: Client, settings: Settings, test_data: RecipeCache
) -> None:
    """Test writing a cache file to Google Cloud Storage."""
    plugin = get_cache_plugin()
    async with plugin:
        await plugin.set_item(TEST_RECIPE_NAME, test_data)
        await plugin.save()

    expected_content = {TEST_RECIPE_NAME: test_data}

    # Retrieve with sync client wrapped in executor
    bucket = await asyncio.to_thread(
        gcs_client.get_bucket, settings.cloud_container_name
    )
    blob = bucket.blob(settings.cache_file)
    content = await asyncio.to_thread(blob.download_as_bytes)
    actual_content = json.loads(content.decode("utf-8"))

    assert actual_content == expected_content


@pytest.mark.asyncio
async def test_retrieve_cache_file(
    gcs_client: Client, settings: Settings, test_data: RecipeCache
) -> None:
    """Test retrieving a cache file from Google Cloud Storage."""
    bucket = await asyncio.to_thread(
        gcs_client.get_bucket, settings.cloud_container_name
    )
    blob = bucket.blob(settings.cache_file)
    content = json.dumps({TEST_RECIPE_NAME: test_data})
    await asyncio.to_thread(blob.upload_from_string, content.encode("utf-8"))

    plugin = get_cache_plugin()
    async with plugin:
        actual_content = await plugin.get_item(TEST_RECIPE_NAME)

    assert actual_content == test_data
