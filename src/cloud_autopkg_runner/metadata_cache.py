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


def create_dummy_files(recipe_list: Iterable[str], cache: MetadataCache) -> None:
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

    logger.debug("Dummy files created.")


def get_file_metadata(file_path: Path, attr: str) -> str:
    """Get extended file metadata.

    Args:
        file_path: The path to the file.
        attr: the attribute of the extended metadata.

    Returns:
        The decoded string representation of the extended attribute metadata.
    """
    return cast(
        "bytes",
        xattr.getxattr(  # pyright: ignore[reportUnknownMemberType]
            file_path, attr
        ),
    ).decode()


def load_metadata_cache(file_path: Path) -> MetadataCache:
    """Load the metadata cache from a JSON file.

    Reads the contents of the specified JSON file into a `MetadataCache` dictionary.
    If the file does not exist, it is created with an empty JSON object.

    Args:
        file_path: Path to the metadata cache JSON file.

    Returns:
        A `MetadataCache` dictionary containing the loaded metadata.

    Raises:
        InvalidJsonContents: If the file contains invalid JSON.
    """
    logger.debug(f"Loading metadata cache from {file_path}...")

    if not file_path.exists():
        logger.warning(f"{file_path} does not exist. Creating...")
        file_path.write_text("{}")
        logger.info(f"{file_path} created.")

    try:
        metadata_cache = MetadataCache(json.loads(file_path.read_text()))
        logger.info(f"Metadata cache loaded from {file_path}.")
    except json.JSONDecodeError as exc:
        raise InvalidJsonContents(file_path) from exc

    logger.debug(f"Metadata cache: {metadata_cache}")
    return metadata_cache


def save_metadata_cache(
    file_path: Path, recipe_name: str, metadata: RecipeCache
) -> None:
    """Save a recipes metadata to the cache.

    Args:
        file_path: The path to the metadata cache JSON file.
        recipe_name: The name of the recipe the data is related to.
        metadata: A `RecipeCache` dictionary to store in the file.
    """
    stored_metadata = load_metadata_cache(file_path)

    new_metadata = stored_metadata.copy()
    new_metadata[recipe_name] = metadata

    file_path.write_text(json.dumps(new_metadata, indent=2, sort_keys=True))
