"""Module for managing a metadata cache stored in an S3 bucket.

This module provides an asynchronous implementation of a metadata cache that
stores data in an S3 bucket. To maintain non-blocking behavior, blocking boto3
operations are executed in background threads via `asyncio.to_thread`.

The implementation ensures that only one instance of the cache is created
(singleton pattern) and provides thread-safe methods for loading, saving,
getting, setting, and deleting cache items.
"""

import asyncio
import json
from types import TracebackType
from typing import TYPE_CHECKING

import boto3
from botocore.exceptions import ClientError

from cloud_autopkg_runner import Settings, logging_config
from cloud_autopkg_runner.metadata_cache import MetadataCache, RecipeCache, RecipeName

if TYPE_CHECKING:
    from types_boto3_s3 import S3Client


class AsyncS3Cache:
    """Asynchronous implementation of MetadataCachePlugin for S3 storage.

    This class provides a singleton implementation for managing a metadata cache
    stored in an S3 bucket using boto3. Blocking S3 operations are dispatched to
    background threads to prevent blocking the event loop.

    Attributes:
        _bucket_name: The name of the S3 bucket used for storing the cache data.
        _cache_key: The key (path) within the S3 bucket where the cache data is stored.
        _cache_data: The in-memory representation of the cache data.
        _is_loaded: A flag indicating whether the cache data has been loaded from S3.
        _lock: An asyncio lock used to ensure thread safety and prevent multiple
            coroutines from writing to the S3 object simultaneously.
    """

    _instance: "AsyncS3Cache | None" = None  # Singleton instance
    _lock: asyncio.Lock = asyncio.Lock()  # Asynchronous lock for thread safety

    def __new__(cls) -> "AsyncS3Cache":
        """Singleton implementation.

        This method ensures that only one instance of the `AsyncS3Cache` class
        is created. If an instance already exists, it returns the existing
        instance; otherwise, it creates a new instance.

        Returns:
            The singleton instance of `AsyncS3Cache`.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize the AsyncS3Cache instance."""
        if hasattr(self, "_initialized"):
            return

        settings = Settings()
        self._logger = logging_config.get_logger(__name__)
        self._bucket_name: str = settings.cloud_container_name
        self._cache_key: str = settings.cache_file
        self._cache_data: MetadataCache = {}
        self._is_loaded: bool = False

        self._initialized: bool = True

    async def open(self) -> None:
        """Open the connection to S3.

        Creates an S3 client from a boto3 session and stores it in the `_client`
        variable. The operation is performed in a background thread to avoid
        blocking the event loop.
        """

        def _make_s3_client() -> "S3Client":
            session = boto3.Session()
            return session.client("s3")

        if not hasattr(self, "_client"):
            self._client = await asyncio.to_thread(_make_s3_client)

    async def load(self) -> MetadataCache:
        """Load metadata from the S3 bucket asynchronously.

        Loads the metadata cache from the S3 bucket into memory. This method
        uses an asyncio lock to ensure thread safety and to prevent multiple
        coroutines from loading the cache simultaneously.

        If the object does not exist or if the S3 object is corrupt, it logs a
        warning and returns an empty cache.

        Returns:
            The metadata cache loaded from the S3 bucket.
        """
        if self._is_loaded:
            return self._cache_data

        async with self._lock:
            # Could have loaded while waiting
            if self._is_loaded:
                return self._cache_data

            if not hasattr(self, "_client"):
                await self.open()

            try:
                response = await asyncio.to_thread(
                    self._client.get_object,
                    Bucket=self._bucket_name,
                    Key=self._cache_key,
                )

                body = response["Body"].read()
                self._cache_data = json.loads(body.decode("utf-8"))

                self._logger.info(
                    "Loaded metadata from s3://%s/%s",
                    self._bucket_name,
                    self._cache_key,
                )

            except json.JSONDecodeError:
                self._cache_data = {}
                self._logger.warning(
                    "Metadata object in s3://%s/%s is corrupt, "
                    "initializing an empty cache.",
                    self._bucket_name,
                    self._cache_key,
                )
            except ClientError as exc:
                self._cache_data = {}
                if exc.response.get("Error", {}).get("Code") == "NoSuchKey":
                    self._logger.warning(
                        "Cache not found at s3://%s/%s, initializing an empty cache.",
                        self._bucket_name,
                        self._cache_key,
                    )
                else:
                    self._logger.warning(
                        "Unexpected error loading metadata from s3://%s/%s, "
                        "initializing an empty cache.",
                        self._bucket_name,
                        self._cache_key,
                    )
            finally:
                self._is_loaded = True

        return self._cache_data

    async def save(self) -> None:
        """Write the metadata cache to the S3 bucket.

        Serializes the cache data to JSON and uploads it to the S3 bucket.
        This method uses an asyncio lock to ensure thread safety and executes
        the upload in a background thread.
        """
        async with self._lock:
            if not hasattr(self, "_client"):
                await self.open()

            try:
                content = json.dumps(self._cache_data, indent=4)
                await asyncio.to_thread(
                    self._client.put_object,
                    Bucket=self._bucket_name,
                    Key=self._cache_key,
                    Body=content.encode("utf-8"),
                )
                self._logger.debug(
                    "Saved all metadata to s3://%s/%s",
                    self._bucket_name,
                    self._cache_key,
                )
            except ClientError:
                self._logger.exception(
                    "Error saving metadata to s3://%s/%s",
                    self._bucket_name,
                    self._cache_key,
                )

    async def close(self) -> None:
        """Save cached data and close the S3 connection.

        Ensures that any unsaved cache data is written to S3 and closes the S3
        client connection.
        """
        if hasattr(self, "_client"):
            await self.save()
            self._client.close()
            del self._client

    async def clear_cache(self) -> None:
        """Clear all data from the cache.

        Clears the in-memory cache and resets the load flag, then persists the
        empty cache to S3.
        """
        async with self._lock:
            self._cache_data = {}
            self._is_loaded = True

        await self.save()

    async def get_item(self, recipe_name: RecipeName) -> RecipeCache | None:
        """Retrieve a specific item from the cache asynchronously.

        Args:
            recipe_name: The name of the recipe to retrieve.

        Returns:
            The metadata associated with the recipe, or None if not found.
        """
        await self.load()
        return self._cache_data.get(recipe_name)

    async def set_item(self, recipe_name: RecipeName, value: RecipeCache) -> None:
        """Set a specific item in the cache asynchronously.

        Args:
            recipe_name: The name of the recipe to set.
            value: The metadata to associate with the recipe.
        """
        await self.load()
        async with self._lock:
            self._cache_data[recipe_name] = value
            self._logger.debug(
                "Setting recipe %s to %s in the metadata cache.", recipe_name, value
            )

    async def delete_item(self, recipe_name: RecipeName) -> None:
        """Delete a specific item from the cache asynchronously.

        Args:
            recipe_name: The name of the recipe to delete from the cache.
        """
        await self.load()
        async with self._lock:
            if recipe_name in self._cache_data:
                del self._cache_data[recipe_name]
                self._logger.debug(
                    "Deleted recipe %s from metadata cache.", recipe_name
                )

    async def __aenter__(self) -> "AsyncS3Cache":
        """Enter an async context.

        Called when entering an `async with` block. Opens the S3 connection
        and loads the cache into memory.
        """
        await self.open()
        await self.load()
        return self

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_val: BaseException | None,
        _exc_tb: TracebackType | None,
    ) -> None:
        """Exit the async context.

        Called when exiting an `async with` block to close the connection.

        Args:
            _exc_type: The type of exception that was raised, if any.
            _exc_val: The exception instance that was raised, if any.
            _exc_tb: The traceback associated with the exception, if any.
        """
        await self.close()
