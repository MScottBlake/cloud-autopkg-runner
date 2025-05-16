"""Module for managing a metadata cache stored in an S3 bucket.

This module provides an asynchronous implementation of a metadata cache that
stores data in an S3 bucket. It uses a singleton pattern to ensure that only one
instance of the cache is created, and it provides methods for loading, saving,
getting, setting, and deleting cache items. The cache is thread-safe, using an
asyncio lock to prevent race conditions.
"""

import asyncio
import json
from types import TracebackType
from typing import TYPE_CHECKING

import aioboto3

from cloud_autopkg_runner import Settings, logging_config
from cloud_autopkg_runner.metadata_cache import MetadataCache, RecipeCache, RecipeName

if TYPE_CHECKING:
    from types_aiobotocore_s3 import S3Client


class AsyncS3Cache:
    """Asynchronous implementation of MetadataCachePlugin for S3 storage.

    This class provides a singleton implementation for managing a metadata cache
    stored in an S3 bucket. It supports asynchronous loading, saving, getting,
    setting, and deleting cache items, ensuring thread safety through the use of
    an asyncio lock.

    Attributes:
        _bucket_name: The name of the S3 bucket used for storing the cache data.
        _cache_key: The key (path) within the S3 bucket where the cache data is
            stored.
        _cache_data: The in-memory representation of the cache data.
        _is_loaded: A flag indicating whether the cache data has been loaded from
            the S3 bucket.
        _lock: An asyncio lock used to ensure thread safety and prevents multiple
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

        Creates a boto3 session and s3 client, which are stored to the `_client`
        variable.
        """
        session = aioboto3.Session()
        async with session.client("s3") as s3_client:
            self._client: S3Client = s3_client

    async def load(self) -> MetadataCache:
        """Load metadata from the S3 bucket asynchronously.

        This method loads the metadata cache from the S3 bucket into memory. It uses
        an asyncio lock to ensure thread safety and prevents multiple coroutines from
        loading the cache simultaneously.

        If the object does not exist or if the S3 object is corrupt, it logs a warning
        and returns an empty cache.

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
                response = await self._client.get_object(
                    Bucket=self._bucket_name,
                    Key=self._cache_key,
                )

                content = await response["Body"].read()
                self._cache_data = json.loads(content)
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
            except Exception:
                self._cache_data = {}
                self._logger.exception(
                    "An unexpected error occurred loading the metadata object in "
                    "s3://%s/%s, initializing an empty cache.",
                    self._bucket_name,
                    self._cache_key,
                )
            finally:
                self._is_loaded = True

        return self._cache_data

    async def save(self) -> None:
        """Write the metadata cache to the S3 bucket.

        This method writes the entire metadata cache to the S3 bucket. It uses an
        asyncio lock to ensure thread safety and prevents multiple coroutines
        from writing to the S3 object simultaneously.
        """
        async with self._lock:
            try:
                content = json.dumps(self._cache_data, indent=4)
                await self._client.put_object(
                    Bucket=self._bucket_name,
                    Key=self._cache_key,
                    Body=content.encode("utf-8"),
                )
                self._logger.debug(
                    "Saved all metadata to s3://%s/%s",
                    self._bucket_name,
                    self._cache_key,
                )
            except Exception:
                self._logger.exception(
                    "Error saving metadata to s3://%s/%s",
                    self._bucket_name,
                    self._cache_key,
                )

    async def close(self) -> None:
        """Close the connection to S3.

        This method closes the session and any resources associated with the connection.
        """
        if hasattr(self, "_client"):
            await self._client.close()
            del self._client

    async def clear_cache(self) -> None:
        """Clear all data from the cache."""
        async with self._lock:
            self._cache_data = {}
            self._is_loaded = True

        await self.save()

    async def get_item(self, recipe_name: RecipeName) -> RecipeCache | None:
        """Retrieve a specific item from the cache asynchronously.

        Args:
            recipe_name: The name of the recipe to retrieve.

        Returns:
            The metadata associated with the recipe, or None if the recipe is not
            found in the cache.
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
        """For use in `async with` statements.

        This method is called when entering an `async with` block. It opens the
        cache data from the S3 bucket and returns the `AsyncS3Cache` instance.
        """
        await self.open()
        await self.load()
        return self

    async def __aexit__(
        self,
        _exc_type: TracebackType | None,
        _exc_val: BaseException | None,
        _exc_tb: TracebackType | None,
    ) -> None:
        """For use in `async with` statements.

        This method is called when exiting an `async with` block. It saves the
        cache data to the S3 bucket and releases any resources held by the cache.

        Args:
            _exc_type: The type of exception that was raised, if any.
            _exc_val: The exception instance that was raised, if any.
            _exc_tb: The traceback associated with the exception, if any.
        """
        await self.close()
