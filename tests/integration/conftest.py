import asyncio
import os
import time
import uuid
from collections.abc import AsyncGenerator

import aioboto3
import pytest_asyncio
from azure.storage.blob import StorageErrorCode
from azure.storage.blob.aio import BlobServiceClient
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


# --- Azure Fixtures ---


@pytest_asyncio.fixture(scope="session")
async def azure_blob_service_client() -> AsyncGenerator[BlobServiceClient, None]:
    """Provides a low-level Azure Blob Service Client for session-scoped operations.

    This client is configured to connect to Azurite using its default connection string.
    """
    connection_string = os.environ["AZURE_STORAGE_CONNECTION_STRING"]

    async with BlobServiceClient.from_connection_string(connection_string) as client:
        yield client


@pytest_asyncio.fixture
async def azure_test_container(
    azure_blob_service_client: BlobServiceClient,
) -> AsyncGenerator[str, None]:
    """Creates a temporary Azure Blob Storage container and cleans up after use.

    This async generator yields the name of a uniquely generated Azure container,
    then deletes all blobs within it and removes the container upon completion.
    """
    container_name = (
        generate_unique_name("cloud-autopkg-test-azure").replace("-", "").lower()
    )
    if not container_name[0].isalpha() or not container_name[-1].isalnum():
        container_name = "az" + container_name
    container_name = container_name[:63]

    print(f"Creating Azure container: {container_name}")
    try:
        container_client = azure_blob_service_client.get_container_client(
            container_name
        )
        await container_client.create_container()
        yield container_name
    finally:
        print(f"Cleaning up Azure container: {container_name}")

        # List and delete all blobs
        container_client = azure_blob_service_client.get_container_client(
            container_name
        )
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

    # get_cache_plugin() should return AsyncAzureBlobCache due to settings.cache_plugin
    plugin = get_cache_plugin()
    await plugin.open()
    await plugin.clear_cache()
    yield plugin
    await plugin.close()
