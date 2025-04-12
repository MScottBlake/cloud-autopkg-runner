"""Module for managing the metadata cache used by cloud-autopkg-runner.

This module provides functions for loading, storing, and updating
cached metadata related to AutoPkg recipes. The cache helps improve
performance by reducing the need to repeatedly fetch data from external
sources.

The metadata cache is stored in a JSON file and contains information
about downloaded files, such as their size, ETag, and last modified date.
This information is used to create dummy files for testing purposes and
to avoid unnecessary downloads.
"""

import asyncio
import json
from pathlib import Path
from typing import TypeAlias, TypedDict

from cloud_autopkg_runner import logger
from cloud_autopkg_runner.exceptions import InvalidJsonContents


class DownloadMetadata(TypedDict, total=False):
    """Represents metadata for a downloaded file.

    Attributes:
        etag: The ETag of the downloaded file.
        file_path: The path to the downloaded file.
        file_size: The size of the downloaded file in bytes.
        last_modified: The last modified date of the downloaded file.
    """

    etag: str
    file_path: str
    file_size: int
    last_modified: str


class RecipeCache(TypedDict):
    """Represents the cache data for a recipe.

    Attributes:
        timestamp: The timestamp when the cache data was created.
        metadata: A list of `DownloadMetadata` dictionaries, one for each
            downloaded file associated with the recipe.
    """

    timestamp: str
    metadata: list[DownloadMetadata]


MetadataCache: TypeAlias = dict[str, RecipeCache]
"""Type alias for the metadata cache dictionary.

This type alias represents the structure of the metadata cache, which is a
dictionary mapping recipe names to `RecipeCache` objects.
"""


class MetadataCacheManager:
    """Manages the metadata cache, loading from and saving to disk."""

    _cache: MetadataCache | None = None
    _lock = asyncio.Lock()

    @classmethod
    async def clear_cache(cls) -> None:
        """Clear the in-memory metadata cache.

        This class method resets the in-memory metadata cache to `None`,
        forcing a reload from disk on the next access.
        """
        async with cls._lock:
            cls._cache = None

    @classmethod
    async def load(cls, file_path: Path) -> MetadataCache:
        """Load the metadata cache from disk.

        If the cache is not already loaded, this method loads it from the
        specified file path. It uses a lock to prevent concurrent loads.

        Args:
            file_path: The path to the file where the metadata cache is stored.

        Returns:
            The loaded metadata cache.
        """
        async with cls._lock:
            if cls._cache is None:
                logger.debug("Loading metadata cache for the first time...")
                cls._cache = await asyncio.to_thread(cls._load_from_disk, file_path)
            return cls._cache

    @classmethod
    async def save(
        cls, file_path: Path, recipe_name: str, metadata: RecipeCache
    ) -> None:
        """Save metadata to the cache and persist it to disk.

        This method updates the metadata cache with new recipe metadata and
        then saves the entire cache to disk. It uses a lock to ensure that
        only one save operation occurs at a time.

        Args:
            file_path: The path to the file where the metadata cache is stored.
            recipe_name: The name of the recipe to cache.
            metadata: The metadata associated with the recipe.
        """
        async with cls._lock:
            if cls._cache is None:
                cls._cache = await asyncio.to_thread(cls._load_from_disk, file_path)

            cls._cache = cls._cache.copy()
            cls._cache[recipe_name] = metadata
            await asyncio.to_thread(cls._save_to_disk, file_path, cls._cache)

    @staticmethod
    def _load_from_disk(file_path: Path) -> MetadataCache:
        """Load metadata from disk.

        This static method reads the metadata cache from the specified file.
        If the file does not exist, it creates an empty JSON file.

        Args:
            file_path: The path to the file where the metadata cache is stored.

        Returns:
            The metadata cache loaded from disk.

        Raises:
            InvalidJsonContents: If the JSON contents of the file are invalid.
        """
        if not file_path.exists():
            logger.warning(f"{file_path} does not exist. Creating...")
            file_path.write_text("{}")
            logger.info(f"{file_path} created.")

        try:
            return MetadataCache(json.loads(file_path.read_text()))
        except json.JSONDecodeError as exc:
            raise InvalidJsonContents(file_path) from exc

    @staticmethod
    def _save_to_disk(file_path: Path, metadata_cache: MetadataCache) -> None:
        """Save metadata to disk.

        This static method writes the metadata cache to the specified file
        as a JSON string.

        Args:
            file_path: The path to the file where the metadata cache is stored.
            metadata_cache: The metadata cache to be saved.
        """
        file_path.write_text(json.dumps(metadata_cache, indent=2, sort_keys=True))
        logger.info(f"Metadata cache saved to {file_path}.")
