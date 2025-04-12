"""Module for handling file operations related to AutoPkg.

This module provides utility functions for handling file operations,
specifically related to AutoPkg recipes and metadata caching.

It includes functions for creating dummy files based on cached metadata,
setting file sizes, and retrieving extended file metadata (xattrs).
These functions are designed to be used within asynchronous workflows,
often involving file system interactions and external command execution.

Functions:
    _set_file_size: Sets a file to a specified size by writing a null byte at the end.
    create_dummy_files: Creates dummy files based on metadata from the cache.
    get_file_metadata: Get extended file metadata.
    get_file_size: Get the size of the file.
"""

import asyncio
from collections.abc import Iterable
from pathlib import Path
from typing import cast

import xattr  # pyright: ignore[reportMissingTypeStubs]

from cloud_autopkg_runner import list_possible_file_names, logger
from cloud_autopkg_runner.metadata_cache import DownloadMetadata, MetadataCache


def _set_file_size(file_path: Path, size: int) -> None:
    """Set a file to a specified size by writing a null byte at the end.

    Effectively replicates the behavior of `mkfile -n` on macOS. This function
    does not actually write `size` bytes of data, but rather sets the file's
    metadata to indicate that it is `size` bytes long. This is used to
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

    possible_names: set[str] = set()
    for recipe_name in recipe_list:
        possible_names.update(list_possible_file_names(recipe_name))

    for recipe_name, recipe_cache_data in cache.items():
        if recipe_name not in possible_names:
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
