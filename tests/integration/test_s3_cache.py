import json
from datetime import datetime, timezone

import pytest
from types_aiobotocore_s3 import S3Client

from cloud_autopkg_runner.cache.s3_cache import AsyncS3Cache
from cloud_autopkg_runner.metadata_cache import MetadataCachePlugin, RecipeCache

# Define test data outside of a class
TEST_RECIPE_NAME = "test.pkg.recipe"
TEST_TIMESTAMP_STR = datetime(2023, 10, 26, 10, 30, 0, tzinfo=timezone.utc).isoformat()


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
    new_plugin = AsyncS3Cache()
    contents = await new_plugin.get_item(TEST_RECIPE_NAME)
    assert contents == test_data

    # Retrieve full file with s3 client
    response = await s3_session_client.get_object(
        Bucket=s3_test_bucket, Key="metadata_cache.json"
    )
    async with response["Body"] as stream:
        content = await stream.read()
    actual_s3_content = json.loads(content.decode("utf-8"))

    expected_s3_content_dict = {TEST_RECIPE_NAME: test_data}
    assert actual_s3_content == expected_s3_content_dict
