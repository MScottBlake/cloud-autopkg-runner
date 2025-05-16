"""Module for managing a metadata cache stored in a Google Cloud Storage bucket.

This module provides an asynchronous implementation of a metadata cache that
stores data in a Google Cloud Storage (GCS) bucket. It uses a singleton pattern to
ensure that only one instance of the cache is created and provides methods for
loading, saving, getting, setting, and deleting cache items. The cache is thread-safe,
using an asyncio lock to prevent race conditions.
"""

import asyncio
import json
from types import TracebackType

from google.cloud.storage import Client  # pyright: ignore[reportMissingTypeStubs]

from cloud_autopkg_runner import Settings, logging_config
from cloud_autopkg_runner.metadata_cache import MetadataCache, RecipeCache, RecipeName


class AsyncGCSCache:
    """Asynchronous implementation of MetadataCachePlugin for Google Cloud Storage.

    This class provides a singleton implementation for managing a metadata cache
    stored in a Google Cloud Storage (GCS) bucket. It supports asynchronous loading,
    saving, getting, setting, and deleting cache items, ensuring thread safety
    through the use of an asyncio lock.

    Attributes:
        _bucket_name: The name of the GCS bucket used for storing the cache data.
        _blob_name: The name of the blob within the bucket where the cache data
            is stored.
        _cache_data: The in-memory representation of the cache data.
        _is_loaded: A flag indicating whether the cache data has been loaded from
            Google Cloud Storage.
        _lock: An asyncio lock used to ensure thread safety when accessing or
            modifying the cache data.
    """

    _instance: "AsyncGCSCache | None" = None  # Singleton instance
    _lock: asyncio.Lock = asyncio.Lock()  # Asynchronous lock for thread safety

    def __new__(cls) -> "AsyncGCSCache":
        """Singleton implementation.

        This method ensures that only one instance of the `AsyncGCSCache` class
        is created. If an instance already exists, it returns the existing
        instance; otherwise, it creates a new instance.

        Returns:
            The singleton instance of `AsyncGCSCache`.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize the AsyncGCSCache instance."""
        if hasattr(self, "_initialized"):
            return

        settings = Settings()
        self._logger = logging_config.get_logger(__name__)
        self._bucket_name: str = settings.cloud_container_name
        self._blob_name: str = settings.cache_file
        self._cache_data: MetadataCache = {}
        self._is_loaded: bool = False
        self._client: Client

        self._initialized: bool = True

    async def open(self) -> None:
        """Open the connection to Google Cloud Storage."""
        loop = asyncio.get_event_loop()
        self._client = await loop.run_in_executor(None, Client)

    async def load(self) -> MetadataCache:
        """Load metadata from Google Cloud Storage asynchronously.

        This method loads the metadata cache from Google Cloud Storage into memory. It
        uses an asyncio lock to ensure thread safety and prevents multiple coroutines
        from loading the cache simultaneously.

        Returns:
            The metadata cache loaded from Google Cloud Storage.
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
                bucket = self._client.bucket(self._bucket_name)  # pyright: ignore[reportUnknownMemberType]
                blob = bucket.blob(self._blob_name)  # pyright: ignore[reportUnknownMemberType]

                loop = asyncio.get_event_loop()
                content = await loop.run_in_executor(None, blob.download_as_string)  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]

                self._cache_data = json.loads(content.decode("utf-8"))
                self._logger.info(
                    "Loaded metadata from gcs://%s/%s",
                    self._bucket_name,
                    self._blob_name,
                )
            except Exception:
                self._cache_data = {}
                self._logger.exception(
                    "An unexpected error occurred loading the metadata from "
                    "gcs://%s/%s, initializing an empty cache.",
                    self._bucket_name,
                    self._blob_name,
                )
            finally:
                self._is_loaded = True

        return self._cache_data

    async def save(self) -> None:
        """Write the metadata cache to Google Cloud Storage.

        This method writes the entire metadata cache to Google Cloud Storage. It uses an
        asyncio lock to ensure thread safety and prevents multiple coroutines
        from writing to the blob simultaneously.
        """
        async with self._lock:
            if not hasattr(self, "_client"):
                await self.open()

            try:
                loop = asyncio.get_event_loop()
                content = json.dumps(self._cache_data, indent=4)
                bucket = self._client.bucket(self._bucket_name)  # type: ignore
                blob = bucket.blob(self._blob_name)  # type: ignore
                await loop.run_in_executor(
                    None,
                    blob.upload_from_string,  # type: ignore
                    content.encode("utf-8"),
                    "application/json",
                )

                self._logger.debug(
                    "Saved all metadata to gcs://%s/%s",
                    self._bucket_name,
                    self._blob_name,
                )
            except Exception:
                self._logger.exception(
                    "Error saving metadata to gcs://%s/%s",
                    self._bucket_name,
                    self._blob_name,
                )

    async def close(self) -> None:
        """Close the connection to Google Cloud Storage."""
        if hasattr(self, "_client"):
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._client.close)
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

    async def __aenter__(self) -> "AsyncGCSCache":
        """For use in `async with` statements.

        This method is called when entering an `async with` block. It loads the
        cache data from Google Cloud Storage and returns the `AsyncGCSCache`
        instance.
        """
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
        cache data to Google Cloud Storage and releases any resources held by the cache.

        Args:
            _exc_type: The type of exception that was raised, if any.
            _exc_val: The exception instance that was raised, if any.
            _exc_tb: The traceback associated with the exception, if any.
        """
        await self.close()
