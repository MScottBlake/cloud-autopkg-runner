import asyncio
import json
import time
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

import aioboto3
import pytest
import pytest_asyncio
from types_aiobotocore_s3 import S3Client

from cloud_autopkg_runner import Settings
from cloud_autopkg_runner.cache.s3_cache import AsyncS3Cache
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
    # S3 bucket names have strict rules: no underscores, must be lowercase, max 63 chars
    unique_part = uuid.uuid4().hex[:8]
    timestamp_part = str(int(time.time()))
    sanitized_prefix = prefix.lower().replace("_", "-").replace(".", "-")

    full_name = f"{sanitized_prefix}-{unique_part}-{timestamp_part}"

    # S3 bucket names must start and end with an alphanumeric character
    # and contain only lowercase letters, numbers, and hyphens.
    # Max length 63 characters.
    return full_name[:63].strip("-")


@pytest_asyncio.fixture(scope="session")
async def s3_session_client() -> AsyncGenerator[S3Client, None]:
    """Provides a low-level S3 client for session-scoped operations."""
    session = aioboto3.Session()
    async with session.client(
        "s3", endpoint_url="http://localhost:4566", region_name="us-east-1"
    ) as s3_client:
        yield s3_client


@pytest_asyncio.fixture
async def s3_test_bucket(s3_session_client: S3Client) -> AsyncGenerator[str, None]:
    """Creates a temporary S3 bucket and ensures its cleanup after use.

    This async generator yields the name of a uniquely generated S3 bucket, which can be
    used for test operations. Upon completion, it deletes all objects within the bucket
    and then removes the bucket itself to prevent resource leakage.
    """
    bucket_name = generate_unique_name("cloud-autopkg-test-s3")
    print(f"Creating S3 bucket: {bucket_name}")  # Added print for CI visibility
    try:
        await s3_session_client.create_bucket(Bucket=bucket_name)
        await asyncio.sleep(1)
        yield bucket_name
    finally:
        print(f"Cleaning up S3 bucket: {bucket_name}")  # Added print for CI visibility
        paginator = s3_session_client.get_paginator("list_objects_v2")
        all_objects = []

        async for page in paginator.paginate(Bucket=bucket_name):
            if "Contents" in page:
                all_objects.extend([{"Key": obj["Key"]} for obj in page["Contents"]])

        if all_objects:
            await s3_session_client.delete_objects(
                Bucket=bucket_name, Delete={"Objects": all_objects}
            )

        await s3_session_client.delete_bucket(Bucket=bucket_name)


@pytest_asyncio.fixture
async def s3_cache_plugin(
    s3_test_bucket: str,
) -> AsyncGenerator[MetadataCachePlugin, None]:
    """Provides an initialized AsyncS3Cache plugin pointing to a test bucket."""
    settings = Settings()
    settings.cache_plugin = "s3"
    settings.cloud_container_name = s3_test_bucket
    settings.cache_file = "metadata_cache.json"

    # get_cache_plugin() should return AsyncS3Cache due to settings.cache_plugin
    plugin = get_cache_plugin()
    await plugin.open()
    await plugin.clear_cache()
    yield plugin
    await plugin.close()


# Tests


@pytest.mark.asyncio
async def test_save_cache_file(
    s3_session_client: S3Client,
    s3_test_bucket: str,
    s3_cache_plugin: MetadataCachePlugin,
) -> None:
    """Test writing a cache file to S3 and then reading it back."""
    test_data: RecipeCache = {
        "timestamp": TEST_TIMESTAMP_STR,
        "metadata": [
            {
                "file_path": "/tmp/test-app-1.0.pkg",
                "file_size": 12345,
                "etag": "abcdef12345",
                "last_modified": TEST_TIMESTAMP_STR,
            }
        ],
    }

    await s3_cache_plugin.set_item(TEST_RECIPE_NAME, test_data)
    await s3_cache_plugin.save()

    # Retrieve data with a new plugin (no stored data)
    async with AsyncS3Cache() as new_plugin:
        loaded_data = await new_plugin.get_item(TEST_RECIPE_NAME)
        assert loaded_data == test_data

    # Retrieve full file with s3 client
    response = await s3_session_client.get_object(
        Bucket=s3_test_bucket, Key="metadata_cache.json"
    )
    async with response["Body"] as stream:
        content = await stream.read()
    actual_s3_content = json.loads(content.decode("utf-8"))

    expected_s3_content_dict = {TEST_RECIPE_NAME: test_data}
    assert actual_s3_content == expected_s3_content_dict
