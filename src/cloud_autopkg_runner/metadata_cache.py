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

from importlib.metadata import entry_points
from typing import Protocol, TypeAlias, TypedDict, runtime_checkable

from cloud_autopkg_runner import Settings, logging_config
from cloud_autopkg_runner.exceptions import (
    PluginManagerEntryPointError,
    PluginManagerError,
)


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


RecipeName: TypeAlias = str
"""Type alias for a recipe name.

This type alias represents a recipe name, which is a string.
"""

MetadataCache: TypeAlias = dict[RecipeName, RecipeCache]
"""Type alias for the metadata cache dictionary.

This type alias represents the structure of the metadata cache, which is a
dictionary mapping recipe names to `RecipeCache` objects.
"""


@runtime_checkable
class MetadataCachePlugin(Protocol):
    """Protocol defining the asynchronous interface for metadata caching."""

    async def open(self) -> None:
        """Open the cache and establish a connection to the underlying storage.

        This method is used to open the cache and establish a connection
        to the underlying storage, such as a file or a database.
        """
        ...

    async def load(self) -> MetadataCache:
        """Load the metadata cache from the underlying storage into memory.

        This method is used to load the metadata cache from the underlying
        storage into memory. The cache is represented as a dictionary
        mapping recipe names to `RecipeCache` objects.

        Returns:
            The metadata cache loaded from the underlying storage.
        """
        ...

    async def save(self) -> None:
        """Persist the metadata cache from memory to the underlying storage.

        This method is used to persist the metadata cache from memory
        to the underlying storage, such as a file or a database.
        """
        ...

    async def close(self) -> None:
        """Close the cache, release any resources, and terminate the connection.

        Close the cache, release any resources, and terminate the connection. to the
        underlying storage.
        """
        ...

    async def clear_cache(self) -> None:
        """Empty the cache.

        This method is used to remove all items from the cache, effectively
        resetting it to an empty state.
        """
        ...

    async def get_item(self, recipe_name: RecipeName) -> RecipeCache | None:
        """Retrieve a specific item from the cache asynchronously.

        Args:
            recipe_name: The name of the recipe to retrieve.

        Returns:
            The metadata associated with the recipe, or None if the recipe is not
            found in the cache.
        """
        ...

    async def set_item(self, recipe_name: RecipeName, value: RecipeCache) -> None:
        """Set a specific item in the cache asynchronously.

        Args:
            recipe_name: The name of the recipe to set.
            value: The metadata to associate with the recipe.
        """
        ...

    async def delete_item(self, recipe_name: RecipeName) -> None:
        """Delete a specific item from the cache asynchronously.

        Args:
            recipe_name: The name of the recipe to delete from the cache.
        """
        ...


class PluginManager:
    """Manages metadata cache plugins.

    This class is responsible for loading and managing metadata cache plugins.
    It uses the `importlib.metadata` module to discover available plugins
    and load the one specified in the settings.

    Attributes:
        plugin: The active metadata cache plugin instance.
    """

    _instance: "PluginManager | None" = None

    def __new__(cls) -> "PluginManager":
        """Create a new instance of PluginManager if one doesn't exist.

        This `__new__` method implements the Singleton pattern, ensuring
        that only one instance of the `PluginManager` class is ever created.
        If an instance already exists, it is returned; otherwise, a new
        instance is created and stored for future use.

        Returns:
            The PluginManager instance.
        """
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize the PluginManager.

        This method loads the metadata cache plugin specified in the settings.
        It prevents re-initialization by checking if the `_initialized` attribute
        is already set.
        """
        if hasattr(self, "_initialized"):
            return  # Prevent re-initialization

        self.plugin: MetadataCachePlugin
        self.load_plugin()

        self._initialized = True

    def load_plugin(self) -> None:
        """Loads the metadata cache plugin specified in the settings.

        This method uses the `importlib.metadata` module to discover available
        plugins and load the one specified in the settings. It handles
        potential errors during plugin loading, such as missing entry points
        or import errors, and raises a `PluginManagerError` if an error occurs.

        Raises:
            PluginManagerError: If the specified plugin cannot be loaded.
        """
        logger = logging_config.get_logger(__name__)
        settings = Settings()

        plugin_name = settings.cache_plugin
        try:
            plugins = entry_points(group="cloud_autopkg_runner.cache", name=plugin_name)
            if not plugins:
                raise PluginManagerEntryPointError(plugin_name)

            plugin = plugins[plugin_name]
            plugin_class = plugin.load()
            self.plugin = plugin_class()
            logger.info("Loaded metadata cache plugin: %s", plugin_name)
        except (ImportError, AttributeError, ValueError) as exc:
            raise PluginManagerError(plugin_name) from exc

    def get_plugin(self) -> MetadataCachePlugin:
        """Returns the active metadata cache plugin.

        Returns:
            The active metadata cache plugin instance.
        """
        return self.plugin


def get_cache_plugin() -> MetadataCachePlugin:
    """Returns the active metadata cache plugin instance.

    This function retrieves the active metadata cache plugin instance
    from the `PluginManager` and returns it.

    Returns:
        The active metadata cache plugin instance.
    """
    plugin_manager = PluginManager()
    return plugin_manager.get_plugin()
