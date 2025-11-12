import asyncio
import json
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from botocore.exceptions import ClientError

from cloud_autopkg_runner import Settings
from cloud_autopkg_runner.cache.s3_cache import AsyncS3Cache


@pytest_asyncio.fixture
async def s3_cache() -> Generator[AsyncS3Cache, Any, None]:
    """Fixture to create an AsyncS3Cache instance with mocks."""
    with (
        patch.object(Settings, "_instance", None),
        patch.object(AsyncS3Cache, "_instance", None),
        patch("cloud_autopkg_runner.cache.s3_cache.boto3.Session"),
    ):
        settings = Settings()
        settings.cloud_container_name = "test-bucket"
        settings.cache_file = "metadata_cache.json"

        cache = AsyncS3Cache()
        await cache.open()
        try:
            yield cache
        finally:
            await cache.close()


@pytest.mark.asyncio
async def test_load_cache_success(s3_cache: AsyncS3Cache) -> None:
    """Test loading the cache successfully from S3."""
    mock_body = MagicMock()
    mock_body.read.return_value = b'{"recipe1": {"timestamp": "test", "metadata": []}}'

    s3_cache._client.get_object.return_value = {"Body": mock_body}
    cache_data = await s3_cache.load()

    assert cache_data == {"recipe1": {"timestamp": "test", "metadata": []}}
    assert s3_cache._is_loaded is True
    s3_cache._client.get_object.assert_called_once_with(
        Bucket="test-bucket", Key="metadata_cache.json"
    )


@pytest.mark.asyncio
async def test_load_cache_no_such_key(s3_cache: AsyncS3Cache) -> None:
    """Test loading the cache when the key does not exist in S3."""
    # Create a mock response that mimics the structure of a NoSuchKey error
    error_response = {
        "Error": {
            "Code": "NoSuchKey",
            "Message": "The specified key does not exist.",
        },
        "ResponseMetadata": {
            "RequestId": "12345678901234567890123456789012",
            "HostId": (
                "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
            ),
            "HTTPStatusCode": 404,
            "HTTPHeaders": {
                "content-type": "application/xml",
                "date": "Thu, 09 May 2024 14:00:00 GMT",
                "server": "AmazonS3",
                "content-length": "0",
            },
            "RetryAttempts": 0,
        },
    }
    s3_cache._client.get_object.side_effect = ClientError(error_response, "GetObject")

    cache_data = await s3_cache.load()

    assert cache_data == {}
    assert s3_cache._is_loaded is True


@pytest.mark.asyncio
async def test_load_cache_invalid_json(s3_cache: AsyncS3Cache) -> None:
    """Test loading the cache when the JSON is invalid."""
    mock_body = MagicMock()
    mock_body.read.return_value = b"invalid json"
    s3_cache._client.get_object.return_value = {"Body": mock_body}

    cache_data = await s3_cache.load()

    assert cache_data == {}
    assert s3_cache._is_loaded is True


@pytest.mark.asyncio
async def test_load_cache_skips_if_already_loaded(s3_cache: AsyncS3Cache) -> None:
    """Test that load() does not call S3 if already loaded."""
    s3_cache._is_loaded = True
    s3_cache._cache_data = {"recipe1": {"timestamp": "test"}}

    with patch.object(s3_cache._client, "get_object") as mock_get_object:
        data = await s3_cache.load()
        mock_get_object.assert_not_called()
        assert data == {"recipe1": {"timestamp": "test"}}


@pytest.mark.asyncio
async def test_save_cache_success(s3_cache: AsyncS3Cache) -> None:
    """Test saving the cache successfully to S3."""
    s3_cache._cache_data = {"recipe1": {"timestamp": "test"}}

    await s3_cache.save()

    s3_cache._client.put_object.assert_called_once_with(
        Bucket="test-bucket",
        Key="metadata_cache.json",
        Body=json.dumps({"recipe1": {"timestamp": "test"}}, indent=4).encode("utf-8"),
    )


@pytest.mark.asyncio
async def test_save_cache_handles_upload_failure(s3_cache: AsyncS3Cache) -> None:
    """Test that save() handles upload failure gracefully."""
    s3_cache._client.put_object.side_effect = ClientError(
        {"Error": {"Code": "InternalError"}}, "PutObject"
    )
    s3_cache._cache_data = {"recipe1": {"timestamp": "test"}}
    s3_cache._is_loaded = True

    with patch.object(s3_cache._logger, "exception") as mock_log:
        await s3_cache.save()
        mock_log.assert_called_once_with(
            "Error saving metadata to s3://%s/%s",
            "test-bucket",
            "metadata_cache.json",
        )


@pytest.mark.asyncio
async def test_clear_cache(s3_cache: AsyncS3Cache) -> None:
    """Test clearing the cache."""
    s3_cache._cache_data = {"recipe1": {"timestamp": "test"}}
    s3_cache._is_loaded = True

    await s3_cache.clear_cache()

    assert s3_cache._cache_data == {}
    s3_cache._client.put_object.assert_called_once()
    _args, kwargs = s3_cache._client.put_object.call_args
    assert kwargs["Bucket"] == "test-bucket"
    assert kwargs["Key"] == "metadata_cache.json"
    assert json.loads(kwargs["Body"].decode()) == {}


@pytest.mark.asyncio
async def test_get_item(s3_cache: AsyncS3Cache) -> None:
    """Test getting an item from the cache."""
    s3_cache._is_loaded = True
    s3_cache._cache_data = {"recipe1": {"timestamp": "test", "metadata": []}}

    item = await s3_cache.get_item("recipe1")
    assert item == {"timestamp": "test", "metadata": []}


@pytest.mark.asyncio
async def test_get_item_triggers_load_if_not_loaded(s3_cache: AsyncS3Cache) -> None:
    """Test that get_item() triggers load() if the cache is not loaded."""
    s3_cache._is_loaded = False
    with patch.object(s3_cache, "load", return_value=asyncio.Future()) as mock_load:
        mock_load.return_value.set_result({})
        await s3_cache.get_item("recipe1")
        mock_load.assert_called_once()


@pytest.mark.asyncio
async def test_get_item_returns_none_if_missing(s3_cache: AsyncS3Cache) -> None:
    """Test that get_item() returns None if the key is not found."""
    s3_cache._is_loaded = True
    s3_cache._cache_data = {"recipe1": {"timestamp": "test"}}
    assert await s3_cache.get_item("non_existent") is None


@pytest.mark.asyncio
async def test_set_item(s3_cache: AsyncS3Cache) -> None:
    """Test setting an item in the cache."""
    mock_body = MagicMock()
    mock_body.read.return_value = b"{}"
    s3_cache._client.get_object.return_value = {"Body": mock_body}

    await s3_cache.load()
    await s3_cache.set_item("recipe1", {"timestamp": "test"})

    assert "recipe1" in s3_cache._cache_data
    assert s3_cache._cache_data["recipe1"] == {"timestamp": "test"}


@pytest.mark.asyncio
async def test_delete_item(s3_cache: AsyncS3Cache) -> None:
    """Test deleting an item from the cache."""
    s3_cache._cache_data = {"recipe1": {"timestamp": "test"}}
    s3_cache._is_loaded = True

    await s3_cache.delete_item("recipe1")
    assert "recipe1" not in s3_cache._cache_data


@pytest.mark.asyncio
async def test_delete_non_existent_key(s3_cache: AsyncS3Cache) -> None:
    """Test that delete_item() does not raise if the key does not exist."""
    s3_cache._is_loaded = True
    s3_cache._cache_data = {"recipe1": {"timestamp": "test"}}
    await s3_cache.delete_item("non_existent_key")
    assert "recipe1" in s3_cache._cache_data


@pytest.mark.asyncio
async def test_close_removes_client(s3_cache: AsyncS3Cache) -> None:
    """Test that close() deletes the S3 client."""
    await s3_cache.close()
    assert not hasattr(s3_cache, "_client")
