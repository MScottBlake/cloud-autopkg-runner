import asyncio
import os
import time
import uuid
from collections.abc import AsyncGenerator

import aioboto3
import pytest_asyncio
from types_aiobotocore_s3 import S3Client

from cloud_autopkg_runner import Settings
from cloud_autopkg_runner.metadata_cache import MetadataCachePlugin, get_cache_plugin

# --- Shared Utilities for Cloud Integration Tests ---


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


# --- S3 Fixtures ---


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
    try:
        await s3_session_client.create_bucket(Bucket=bucket_name)
        await asyncio.sleep(1)
        yield bucket_name
    finally:
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
    """Provides an initialized AsyncS3Cache plugin pointing to a test bucket.

    This fixture assumes AsyncS3Cache automatically picks up S3 configuration
    (bucket name, key name, endpoint, credentials) from environment variables.
    """
    settings = Settings()
    settings.cache_plugin = "s3"
    settings.cloud_container_name = s3_test_bucket
    settings.cache_file = "metadata_cache.json"

    os.environ["AWS_ENDPOINT_URL"] = "http://localhost:4566"

    # This should pick up the LocalStack endpoint from environment vars.
    plugin = get_cache_plugin()
    await plugin.open()
    await plugin.clear_cache()
    yield plugin
    await plugin.close()
