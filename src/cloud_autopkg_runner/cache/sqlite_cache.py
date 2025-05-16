"""Module for managing a metadata cache stored in a SQLite database.

This module provides an asynchronous implementation of a metadata cache that
stores data in a SQLite database. It uses a singleton pattern to ensure that only one
instance of the cache is created, and it provides methods for loading, saving,
getting, setting, and deleting cache items. The cache is thread-safe, using an
asyncio lock to prevent race conditions.
"""

import asyncio
import json
import sqlite3
from pathlib import Path
from types import TracebackType
from typing import Any, TypeAlias

from cloud_autopkg_runner import Settings, logging_config
from cloud_autopkg_runner.metadata_cache import MetadataCache, RecipeCache, RecipeName


class AsyncSQLiteCache:
    """Asynchronous implementation of MetadataCachePlugin for SQLite storage.

    This class provides a singleton implementation for managing a metadata cache
    stored in a SQLite database. It supports asynchronous loading, saving, getting,
    setting, and deleting cache items, ensuring thread safety through the use of
    an asyncio lock.

    Attributes:
        _db_path: The path to the SQLite database file.
        _cache_data: The in-memory representation of the cache data.
        _is_loaded: A flag indicating whether the cache data has been loaded from
            the SQLite database.
        _lock: An asyncio lock used to ensure thread safety when accessing or
            modifying the cache data.
    """

    _instance: "AsyncSQLiteCache | None" = None  # Singleton instance
    _lock: asyncio.Lock = asyncio.Lock()  # Asynchronous lock for thread safety
    SqlParams: TypeAlias = tuple[Any, ...]

    def __new__(cls) -> "AsyncSQLiteCache":
        """Singleton implementation.

        This method ensures that only one instance of the `AsyncSQLiteCache`
        class is created. If an instance already exists, it returns the existing
        instance; otherwise, it creates a new instance.

        Returns:
            The singleton instance of `AsyncSQLiteCache`.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize the AsyncSQLiteCache instance."""
        if hasattr(self, "_initialized"):
            return

        settings = Settings()
        self._logger = logging_config.get_logger(__name__)
        self._db_path: Path = Path(settings.cache_file)
        self._cache_data: MetadataCache = {}
        self._is_loaded: bool = False
        self._conn: sqlite3.Connection

        self._initialized: bool = True

    async def open(self) -> None:
        """Open the connection to the SQLite database."""
        loop = asyncio.get_event_loop()
        self._conn = await loop.run_in_executor(
            None, lambda: sqlite3.connect(self._db_path, check_same_thread=False)
        )
        await self._create_table()

    async def load(self) -> MetadataCache:
        """Load metadata from the SQLite database asynchronously.

        This method loads the metadata cache from the SQLite database into memory. It
        uses an asyncio lock to ensure thread safety and prevents multiple coroutines
        from loading the cache simultaneously.

        If the database does not exist or if the database is corrupt, it logs a warning
        and returns an empty cache.

        Returns:
            The metadata cache loaded from the SQLite database.
        """
        if self._is_loaded:
            return self._cache_data

        async with self._lock:
            # Could have loaded while waiting
            if self._is_loaded:
                return self._cache_data

            try:
                rows = await self._execute_sql(
                    "SELECT recipe_name, cache_data FROM metadata"
                )

                self._cache_data = {
                    recipe_name: json.loads(cache_data)
                    for recipe_name, cache_data in rows
                }
                self._logger.info("Loaded metadata from %s", self._db_path)
            except FileNotFoundError:
                self._cache_data = {}
                self._logger.warning(
                    "Metadata database not found: %s, initializing an empty cache.",
                    self._db_path,
                )
            except Exception:
                self._cache_data = {}
                self._logger.exception(
                    "An unexpected error occurred loading the metadata from %s, "
                    "initializing an empty cache.",
                    self._db_path,
                )
            finally:
                self._is_loaded = True

        return self._cache_data

    async def save(self) -> None:
        """Write the metadata cache to the SQLite database.

        This method writes the entire metadata cache to the SQLite database. It uses an
        asyncio lock to ensure thread safety and prevents multiple coroutines
        from writing to the database simultaneously.
        """
        try:
            for recipe_name, cache_data in self._cache_data.items():
                await self._execute_sql(
                    "INSERT INTO metadata (recipe_name, cache_data) VALUES (?, ?)",
                    (recipe_name, json.dumps(cache_data)),
                )

            self._logger.debug("Saved all metadata to %s", self._db_path)
        except Exception:
            self._logger.exception("Error saving metadata to %s", self._db_path)

    async def close(self) -> None:
        """Close the database connection."""
        if hasattr(self, "_conn"):
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._conn.close)
            del self._conn

    async def clear_cache(self) -> None:
        """Clear all data from the cache."""
        async with self._lock:
            self._cache_data = {}
            self._is_loaded = True
            await self._clear_table()
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

    async def _execute_sql(
        self, sql: str, parameters: "SqlParams" = ()
    ) -> list[tuple[Any, ...]]:
        if not hasattr(self, "_conn"):
            await self.open()

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._execute_sql_sync, sql, parameters)

    def _execute_sql_sync(
        self, sql: str, parameters: "SqlParams" = ()
    ) -> list[tuple[str | bytes, ...]]:
        """Execute SQL queries (blocking)."""
        cursor = self._conn.cursor()
        cursor.execute(sql, parameters)
        if sql.lower().startswith("select"):
            rows = cursor.fetchall()
        else:
            rows = []
            self._conn.commit()
        cursor.close()
        return rows

    async def _create_table(self) -> None:
        """Create the table in the SQLite database.

        This method creates the `metadata` table in the SQLite database if it
        does not already exist. The table has two columns: `recipe_name` (TEXT)
        and `cache_data` (TEXT).
        """
        try:
            await self._execute_sql(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    recipe_name TEXT PRIMARY KEY,
                    cache_data TEXT
                )
                """
            )
        except Exception:
            self._logger.exception("An unexpected error occurred.")
            raise

    async def _clear_table(self) -> None:
        """Helper method to clear the SQLite database table.

        This method clears the entire `metadata` table in the SQLite database. It uses
        asyncio lock to ensure thread safety and prevents multiple coroutines
        from writing to the database simultaneously.
        """
        try:
            await self._execute_sql("DELETE FROM metadata")
            self._logger.debug("Cleared all metadata from %s", self._db_path)
        except Exception:
            self._logger.exception("Error clearing metadata from %s", self._db_path)

    async def __aenter__(self) -> "AsyncSQLiteCache":
        """For use in `async with` statements.

        This method is called when entering an `async with` block. It opens the
        cache data connection to the SQLite database and returns the `AsyncSQLiteCache`
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
        cache data to the SQLite database and releases any resources held by the cache.

        Args:
            _exc_type: The type of exception that was raised, if any.
            _exc_val: The exception instance that was raised, if any.
            _exc_tb: The traceback associated with the exception, if any.
        """
        await self.close()
