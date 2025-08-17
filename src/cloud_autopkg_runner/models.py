"""Module defining structured data used throughout Cloud AutoPkg Runner.

It provides strongly typed structures for:
- Metadata related to downloaded files (`URLDownloaderMetadata`).
- Cached data for recipes (`RecipeCache`).
- The expected structure of AutoPkg recipe files (`RecipeContents`).
- Reporting structures for recipe run failures and summaries (`RecipeReportFailedItem`,
  `RecipeReportSummaryResults`, `RecipeReportContents`).
- A consolidated view of a recipe run's outcomes (`ConsolidatedReport`).

These definitions enhance type safety, readability, and IDE support for
data structures passed between different components.
"""

from typing import Any, TypeAlias, TypedDict


class URLDownloaderMetadata(TypedDict, total=False):
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
        metadata: A list of `URLDownloaderMetadata` dictionaries, one for each
            downloaded file associated with the recipe.
    """

    timestamp: str
    metadata: list[URLDownloaderMetadata]


RecipeName: TypeAlias = str
"""Type alias for a recipe name.

This type alias represents a recipe name, which is a string.
"""


class RecipeContents(TypedDict):
    """Represents the structure of a recipe's contents.

    This dictionary represents the parsed contents of an AutoPkg recipe file,
    including its description, identifier, input variables, minimum version,
    parent recipe, and process steps.

    Attributes:
        Description: A brief description of the recipe.
        Identifier: A unique identifier for the recipe.
        Input: A dictionary of input variables used by the recipe.
        MinimumVersion: The minimum AutoPkg version required to run the recipe.
        ParentRecipe: The identifier of the recipe's parent recipe (if any).
        Process: A list of dictionaries, where each dictionary defines a step
            in the recipe's processing workflow.
    """

    Description: str | None
    Identifier: str
    Input: dict[str, Any]
    MinimumVersion: str | None
    ParentRecipe: str | None
    Process: list[dict[str, Any]]


MetadataCache: TypeAlias = dict[RecipeName, RecipeCache]
"""Type alias for the metadata cache dictionary.

This type alias represents the structure of the metadata cache, which is a
dictionary mapping recipe names to `RecipeCache` objects.
"""


class RecipeReportFailedItem(TypedDict):
    """Represents a failed item in a recipe report.

    Attributes:
        message: A string containing the error message.
        recipe: A string containing the name of the recipe that failed.
        traceback: A string containing the traceback information.
    """

    message: str
    recipe: str
    traceback: str


class RecipeReportSummaryResults(TypedDict):
    """Represents summary results in a recipe report.

    Attributes:
        header: A list of strings representing the header row of the summary table.
        summary_text: A string containing a summary of the results.
        data_rows: A list of dictionaries, where each dictionary represents a row
            in the summary table.
    """

    header: list[str]
    summary_text: str
    data_rows: list[dict[str, Any]]


class RecipeReportContents(TypedDict):
    """Represents the contents of a recipe report.

    Attributes:
        failures: A list of RecipeReportFailedItem dictionaries, representing
            the items that failed during the recipe run.
        summary_results: A dictionary mapping summary result keys to
            RecipeReportSummaryResults dictionaries.
    """

    failures: list[RecipeReportFailedItem]
    summary_results: dict[str, RecipeReportSummaryResults]


class ConsolidatedReport(TypedDict):
    """Represents a consolidated report of a recipe run.

    This TypedDict combines information from various parts of the
    RecipeReport to provide a summary of the recipe's execution.

    Attributes:
        failed_items: A list of RecipeReportFailedItem dictionaries, representing
            the items that failed during the recipe run.
        downloaded_items: A list of dictionaries representing the files that
            were downloaded during the recipe run.
        pkg_built_items: A list of dictionaries representing the packages
            that were built during the recipe run.
        munki_imported_items: A list of dictionaries representing the items
            that were imported into Munki during the recipe run.
    """

    failed_items: list[RecipeReportFailedItem]
    downloaded_items: list[dict[str, Any]]
    pkg_built_items: list[dict[str, Any]]
    munki_imported_items: list[dict[str, Any]]
