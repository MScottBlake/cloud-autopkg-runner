"""Module for managing a metadata cache stored in an Azure Blob Storage container.

This module provides an asynchronous implementation of a metadata cache that
stores data in an Azure Blob Storage container. It uses a singleton pattern to ensure
that only one instance of the cache is created and provides methods for loading,
saving, getting, setting, and deleting cache items. The cache is thread-safe, using
an asyncio lock to prevent race conditions.
"""

import asyncio
import json
from types import TracebackType

from azure.identity.aio import DefaultAzureCredential
from azure.storage.blob.aio import BlobClient, BlobServiceClient

from cloud_autopkg_runner import Settings, logging_config
from cloud_autopkg_runner.metadata_cache import MetadataCache, RecipeCache, RecipeName


class AsyncAzureBlobCache:
    """Asynchronous implementation of MetadataCachePlugin for Azure Blob Storage.

    This class provides a singleton implementation for managing a metadata cache
    stored in an Azure Blob Storage container. It supports asynchronous loading,
    saving, getting, setting, and deleting cache items, ensuring thread safety
    through the use of an asyncio lock.

    Attributes:
        _container_name: The name of the Azure Blob Storage container used for
            storing the cache data.
        _blob_name: The name of the blob within the container where the cache data
            is stored.
        _cache_data: The in-memory representation of the cache data.
        _is_loaded: A flag indicating whether the cache data has been loaded from
            Azure Blob Storage.
        _lock: An asyncio lock used to ensure thread safety when accessing or
            modifying the cache data.
    """

    _instance: "AsyncAzureBlobCache | None" = None  # Singleton instance
    _lock: asyncio.Lock = asyncio.Lock()  # Asynchronous lock for thread safety

    def __new__(cls) -> "AsyncAzureBlobCache":
        """Singleton implementation.

        This method ensures that only one instance of the `AsyncAzureBlobCache`
        class is created. If an instance already exists, it returns the existing
        instance; otherwise, it creates a new instance.

        Returns:
            The singleton instance of `AsyncAzureBlobCache`.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize the AsyncAzureBlobCache instance."""
        if hasattr(self, "_initialized"):
            return

        settings = Settings()
        self._logger = logging_config.get_logger(__name__)
        self._account_url: str = settings.azure_account_url
        self._container_name: str = settings.cloud_container_name
        self._blob_name: str = settings.cache_file
        self._cache_data: MetadataCache = {}
        self._is_loaded: bool = False
        self._client: BlobClient

        self._initialized: bool = True

    async def open(self) -> None:
        """Open the connection to Azure Blob Storage."""
        blob_service_client: BlobServiceClient = BlobServiceClient(
            self._account_url, DefaultAzureCredential()
        )
        self._client: BlobClient = blob_service_client.get_blob_client(
            container=self._container_name, blob=self._blob_name
        )

    async def load(self) -> MetadataCache:
        """Load metadata from Azure Blob Storage asynchronously.

        This method loads the metadata cache from Azure Blob Storage into memory. It
        uses an asyncio lock to ensure thread safety and prevents multiple coroutines
        from loading the cache simultaneously.

        Returns:
            The metadata cache loaded from Azure Blob Storage.
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
                downloader = await self._client.download_blob(encoding="utf-8")
                content = await downloader.readall()
                self._cache_data = json.loads(content)
                self._logger.info(
                    "Loaded metadata from azure://%s/%s",
                    self._container_name,
                    self._blob_name,
                )
            except Exception:
                self._cache_data = {}
                self._logger.exception(
                    "An unexpected error occurred loading the metadata from "
                    "azure://%s/%s, initializing an empty cache.",
                    self._container_name,
                    self._blob_name,
                )
            finally:
                self._is_loaded = True

        return self._cache_data

    async def save(self) -> None:
        """Write the metadata cache to Azure Blob Storage.

        This method writes the entire metadata cache to Azure Blob Storage. It uses an
        asyncio lock to ensure thread safety and prevents multiple coroutines
        from writing to the blob simultaneously.
        """
        async with self._lock:
            if not hasattr(self, "_client"):
                await self.open()

            try:
                content = json.dumps(self._cache_data, indent=4)
                await self._client.upload_blob(content.encode("utf-8"), overwrite=True)
                self._logger.debug(
                    "Saved all metadata to azure://%s/%s",
                    self._container_name,
                    self._blob_name,
                )
            except Exception:
                self._logger.exception(
                    "Error saving metadata to azure://%s/%s",
                    self._container_name,
                    self._blob_name,
                )

    async def close(self) -> None:
        """Close the connection to Azure Blob Storage."""
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

    async def __aenter__(self) -> "AsyncAzureBlobCache":
        """For use in `async with` statements.

        This method is called when entering an `async with` block. It loads the
        cache data from Azure Blob Storage and returns the `AsyncAzureBlobCache`
        instance.
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
        """For use in `async with` statements.

        This method is called when exiting an `async with` block. It saves the
        cache data to Azure Blob Storage and releases any resources held by the cache.

        Args:
            _exc_type: The type of exception that was raised, if any.
            _exc_val: The exception instance that was raised, if any.
            _exc_tb: The traceback associated with the exception, if any.
        """
        await self.close()
