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
from collections.abc import Iterable
from pathlib import Path
from typing import TypeAlias, TypedDict, cast

import xattr  # pyright: ignore[reportMissingTypeStubs]

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


def _set_file_size(file_path: Path, size: int) -> None:
    """Set a file to a specified size by writing a null byte at the end.

    Effectively replicates the behavior of `mkfile -n` on macOS. This function
    does not actually write `size` bytes of data, but rather sets the file's
    metadata to indicate that it is `size` bytes long.  This is used to
    quickly create dummy files for testing.

    Args:
        file_path: The path to the file.
        size: The desired size of the file in bytes.
    """
    with file_path.open("wb") as f:
        f.seek(int(size) - 1)
        f.write(b"\0")


async def create_dummy_files(recipe_list: Iterable[str], cache: MetadataCache) -> None:
    """Create dummy files based on metadata from the cache.

    For each recipe in the `recipe_list`, this function iterates through the
    download metadata in the `cache`. If a file path (`file_path`) is present
    in the metadata and the file does not already exist, a dummy file is created
    with the specified size and extended attributes (etag, last_modified).

    This function is primarily used for testing and development purposes,
    allowing you to simulate previous downloads without actually downloading
    the files.

    Args:
        recipe_list: An iterable of recipe names to process.
        cache: The metadata cache dictionary.
    """
    logger.debug("Creating dummy files...")

    tasks: list[asyncio.Task[None]] = []

    for recipe_name, recipe_cache_data in cache.items():
        if recipe_name not in recipe_list:
            continue

        logger.info(f"Creating dummy files for {recipe_name}...")
        for metadata_cache in recipe_cache_data.get("metadata", []):
            if not metadata_cache.get("file_path"):
                logger.warning(
                    "Skipping file creation: "
                    f"Missing 'file_path' in {recipe_name} cache"
                )
                continue
            if not metadata_cache.get("file_size"):
                logger.warning(
                    "Skipping file creation: "
                    f"Missing 'file_size' in {recipe_name} cache"
                )
                continue

            file_path = Path(metadata_cache.get("file_path", ""))
            if file_path.exists():
                logger.info(f"Skipping file creation: {file_path} already exists.")
                continue

            # Add the task to create the file, set its size, and set extended attributes
            task = asyncio.create_task(
                asyncio.to_thread(_create_and_set_attrs, file_path, metadata_cache)
            )
            tasks.append(task)

    # Await all the tasks
    await asyncio.gather(*tasks)
    logger.debug("Dummy files created.")


def _create_and_set_attrs(file_path: Path, metadata_cache: DownloadMetadata) -> None:
    """Create the file, set its size, and set extended attributes."""
    # Create parent directory if needed
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # Create file
    file_path.touch()

    # Set file size
    _set_file_size(file_path, metadata_cache.get("file_size", 0))

    # Set extended attributes
    if metadata_cache.get("etag"):
        xattr.setxattr(  # pyright: ignore[reportUnknownMemberType]
            file_path,
            "com.github.autopkg.etag",
            metadata_cache.get("etag", "").encode("utf-8"),
        )
    if metadata_cache.get("last_modified"):
        xattr.setxattr(  # pyright: ignore[reportUnknownMemberType]
            file_path,
            "com.github.autopkg.last-modified",
            metadata_cache.get("last_modified", "").encode("utf-8"),
        )


async def get_file_metadata(file_path: Path, attr: str) -> str:
    """Get extended file metadata.

    Args:
        file_path: The path to the file.
        attr: the attribute of the extended metadata.

    Returns:
        The decoded string representation of the extended attribute metadata.
    """
    return await asyncio.to_thread(
        lambda: cast(
            "bytes",
            xattr.getxattr(  # pyright: ignore[reportUnknownMemberType]
                file_path, attr
            ),
        ).decode()
    )


async def get_file_size(file_path: Path) -> int:
    """Get the size of file.

    Args:
        file_path: The path to the file.

    Returns:
        The file size in bytes, represented as an integer.
    """
    return await asyncio.to_thread(lambda: file_path.stat().st_size)


class MetadataCacheManager:
    """Manages the metadata cache, loading from and saving to disk."""

    _cache: MetadataCache | None = None
    _lock = asyncio.Lock()

    @classmethod
    async def load(cls, file_path: Path) -> MetadataCache:
        """Load the metadata cache from disk.

        If the cache is not already loaded, this method loads it from the
        specified file path.  It uses a lock to prevent concurrent loads.

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
        then saves the entire cache to disk.  It uses a lock to ensure that
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
