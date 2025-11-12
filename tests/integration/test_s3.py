import json
import time
import uuid
from collections.abc import Generator
from datetime import datetime, timezone
from typing import Any

import boto3
import pytest
from types_boto3_s3 import S3Client

from cloud_autopkg_runner import Settings
from cloud_autopkg_runner.metadata_cache import RecipeCache, get_cache_plugin

# Define test data outside of a class
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
    settings.cache_plugin = "s3"
    settings.cloud_container_name = generate_unique_name("cloud-autopkg-test-s3")
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
                "file_path": "/tmp/s3-test-app-1.0.pkg",
                "file_size": 54321,
                "etag": "fedcba98765",
                "last_modified": TEST_TIMESTAMP_STR,
            }
        ],
    }


@pytest.fixture
def s3_client(settings: Settings) -> Generator[S3Client, Any, None]:
    """Fixture that provides a valid S3Client."""
    session = boto3.Session()
    s3_client: S3Client = session.client("s3")
    try:
        s3_client.create_bucket(Bucket=settings.cloud_container_name)

        yield s3_client

        s3_client.delete_object(
            Bucket=settings.cloud_container_name, Key=settings.cache_file
        )
        s3_client.delete_bucket(Bucket=settings.cloud_container_name)
    finally:
        s3_client.close()


# Tests


@pytest.mark.asyncio
async def test_save_cache_file(
    s3_client: S3Client, settings: Settings, test_data: RecipeCache
) -> None:
    """Test writing a cache file to AWS S3."""
    # Store with plugin
    plugin = get_cache_plugin()
    async with plugin:
        await plugin.set_item(TEST_RECIPE_NAME, test_data)
        await plugin.save()

    expected_content = {TEST_RECIPE_NAME: test_data}

    # Retrieve with standard tooling
    response = s3_client.get_object(
        Bucket=settings.cloud_container_name, Key=settings.cache_file
    )
    content = response["Body"].read()
    actual_content = json.loads(content.decode("utf-8"))

    assert actual_content == expected_content


@pytest.mark.asyncio
async def test_retrieve_cache_file(
    s3_client: S3Client, settings: Settings, test_data: RecipeCache
) -> None:
    """Test retrieving a cache file from AWS S3."""
    # Store with standard tooling
    content = json.dumps({TEST_RECIPE_NAME: test_data})
    s3_client.put_object(
        Bucket=settings.cloud_container_name, Key=settings.cache_file, Body=content
    )

    # Retrieve with plugin
    plugin = get_cache_plugin()
    async with plugin:
        actual_content = await plugin.get_item(TEST_RECIPE_NAME)

    assert actual_content == test_data
