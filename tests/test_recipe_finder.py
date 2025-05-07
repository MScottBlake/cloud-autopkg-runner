"""Tests for the recipe_finder module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cloud_autopkg_runner import AutoPkgPrefs, RecipeFinder
from cloud_autopkg_runner.exceptions import RecipeLookupException


@pytest.fixture
def recipe_finder(tmp_path: Path) -> RecipeFinder:
    """Fixture for creating a RecipeFinder instance with a mock AutoPkgPrefs object.

    Returns:
        RecipeFinder: A RecipeFinder object.
    """
    mock_prefs = MagicMock(spec=AutoPkgPrefs)
    mock_prefs.recipe_override_dirs = [tmp_path / "override"]
    mock_prefs.recipe_search_dirs = [tmp_path / "search"]

    finder = RecipeFinder(autopkg_preferences=mock_prefs)
    finder.logger = MagicMock()  # Mock the logger to avoid actual logging
    return finder


@pytest.mark.parametrize(
    ("recipe_name", "expected_names"),
    [
        (
            "MyRecipe",
            ["MyRecipe.recipe", "MyRecipe.recipe.plist", "MyRecipe.recipe.yaml"],
        ),
        ("MyRecipe.recipe", ["MyRecipe.recipe"]),
        ("MyRecipe.recipe.plist", ["MyRecipe.recipe.plist"]),
        ("MyRecipe.recipe.yaml", ["MyRecipe.recipe.yaml"]),
        (
            "MyRecipe.anything",
            [
                "MyRecipe.anything.recipe",
                "MyRecipe.anything.recipe.plist",
                "MyRecipe.anything.recipe.yaml",
            ],
        ),
    ],
    ids=["no_suffix", "recipe_suffix", "plist_suffix", "yaml_suffix", "random_name"],
)
def test_possible_file_names(
    recipe_finder: RecipeFinder, recipe_name: str, expected_names: list[str]
) -> None:
    """Tests list possible file names function based on naming structures.

    This test verifies that the list_possible_file_names function correctly
    generates the expected list of file names for various recipe names,
    including those with and without a file extension, using pytest's
    parameterization feature.
    """
    result = recipe_finder.possible_file_names(recipe_name)
    assert result == expected_names


def test_path_within_depth(tmp_path: Path) -> None:
    """Test _path_within_depth static method."""
    base_path = tmp_path
    candidate_path = tmp_path / "subdir" / "file.txt"
    max_depth = 2

    assert RecipeFinder._path_within_depth(base_path, candidate_path, max_depth) is True
    assert RecipeFinder._path_within_depth(base_path, candidate_path, 1) is False


def test_path_within_depth_outside_base(tmp_path: Path) -> None:
    """Test _path_within_depth when candidate is not within the base path."""
    base_path = tmp_path / "base"
    candidate_path = tmp_path / "other" / "file.txt"
    max_depth = 2

    assert (
        RecipeFinder._path_within_depth(base_path, candidate_path, max_depth) is False
    )


@pytest.mark.asyncio
async def test_find_recursively_found(
    recipe_finder: RecipeFinder, tmp_path: Path
) -> None:
    """Test _find_recursively method when the target file is found."""
    search_dir = tmp_path / "search"
    search_dir.mkdir(parents=True, exist_ok=True)
    (search_dir / "subdir").mkdir(exist_ok=True)
    target_file = search_dir / "subdir" / "MyRecipe.recipe"
    target_file.write_text("Recipe content")

    found_path = await recipe_finder._find_recursively(
        search_dir, "MyRecipe.recipe", recipe_finder.max_recursion_depth
    )
    assert found_path == target_file


@pytest.mark.asyncio
async def test_find_recursively_not_found(
    recipe_finder: RecipeFinder, tmp_path: Path
) -> None:
    """Test _find_recursively method when the target file is not found."""
    search_dir = tmp_path / "search"
    search_dir.mkdir(parents=True, exist_ok=True)

    found_path = await recipe_finder._find_recursively(
        search_dir, "NonExistent.recipe", recipe_finder.max_recursion_depth
    )
    assert found_path is None


def test_find_in_directory_found(recipe_finder: RecipeFinder, tmp_path: Path) -> None:
    """Test _find_in_directory method when the target file is found."""
    search_dir = tmp_path / "search"
    search_dir.mkdir(parents=True, exist_ok=True)
    target_file = search_dir / "MyRecipe.recipe"
    target_file.write_text("Recipe content")

    found_path = recipe_finder._find_in_directory(search_dir, ["MyRecipe.recipe"])
    assert found_path == target_file


def test_find_in_directory_not_found(
    recipe_finder: RecipeFinder, tmp_path: Path
) -> None:
    """Test _find_in_directory method when the target file is not found."""
    search_dir = tmp_path / "search"
    search_dir.mkdir(parents=True, exist_ok=True)

    found_path = recipe_finder._find_in_directory(search_dir, ["NonExistent.recipe"])
    assert found_path is None


@pytest.mark.asyncio
async def test_find_in_directory_recursively_found(
    recipe_finder: RecipeFinder, tmp_path: Path
) -> None:
    """Test that the target file is found recursively."""
    search_dir = tmp_path / "search"
    search_dir.mkdir(parents=True, exist_ok=True)
    (search_dir / "subdir").mkdir(exist_ok=True)
    target_file = search_dir / "subdir" / "MyRecipe.recipe"
    target_file.write_text("Recipe content")

    found_path = await recipe_finder._find_in_directory_recursively(
        search_dir, ["MyRecipe.recipe"]
    )
    assert found_path == target_file


@pytest.mark.asyncio
async def test_find_in_directory_recursively_not_found(
    recipe_finder: RecipeFinder, tmp_path: Path
) -> None:
    """Test that the target file is not found recursively."""
    search_dir = tmp_path / "search"
    search_dir.mkdir(parents=True, exist_ok=True)

    found_path = await recipe_finder._find_in_directory_recursively(
        search_dir, ["NonExistent.recipe"]
    )
    assert found_path is None


@pytest.mark.asyncio
async def test_search_directory_direct_match(
    recipe_finder: RecipeFinder, tmp_path: Path
) -> None:
    """Test _search_directory method with a direct match."""
    search_dir = tmp_path / "search"
    search_dir.mkdir(parents=True, exist_ok=True)
    target_file = search_dir / "MyRecipe.recipe"
    target_file.write_text("Recipe content")

    found_path = await recipe_finder._search_directory(search_dir, ["MyRecipe.recipe"])
    assert found_path == target_file


@pytest.mark.asyncio
async def test_search_directory_recursive_match(
    recipe_finder: RecipeFinder, tmp_path: Path
) -> None:
    """Test _search_directory method with a recursive match."""
    search_dir = tmp_path / "search"
    search_dir.mkdir(parents=True, exist_ok=True)
    (search_dir / "subdir").mkdir(exist_ok=True)
    target_file = search_dir / "subdir" / "MyRecipe.recipe"
    target_file.write_text("Recipe content")

    found_path = await recipe_finder._search_directory(search_dir, ["MyRecipe.recipe"])
    assert found_path == target_file


@pytest.mark.asyncio
async def test_search_directory_not_found(
    recipe_finder: RecipeFinder, tmp_path: Path
) -> None:
    """Test _search_directory method when the target file is not found."""
    search_dir = tmp_path / "search"
    search_dir.mkdir(parents=True, exist_ok=True)

    found_path = await recipe_finder._search_directory(
        search_dir, ["NonExistent.recipe"]
    )
    assert found_path is None


@pytest.mark.asyncio
async def test_find_recipe_direct_match(
    recipe_finder: RecipeFinder, tmp_path: Path
) -> None:
    """Test find_recipe method with a direct match in lookup directories."""
    recipe_file = tmp_path / "override" / "MyRecipe.recipe"
    tmp_path.joinpath("override").mkdir(parents=True)
    recipe_file.write_text("Recipe content")

    found_path = await recipe_finder.find_recipe("MyRecipe.recipe")
    assert found_path == recipe_file


@pytest.mark.asyncio
async def test_find_recipe_recursive_match(
    recipe_finder: RecipeFinder, tmp_path: Path
) -> None:
    """Test find_recipe method with a recursive match in lookup directories."""
    recipe_file = tmp_path / "search" / "subdir" / "MyRecipe.recipe"
    tmp_path.joinpath("search", "subdir").mkdir(parents=True)
    recipe_file.write_text("Recipe content")

    found_path = await recipe_finder.find_recipe("MyRecipe.recipe")
    assert found_path == recipe_file


@pytest.mark.asyncio
async def test_find_recipe_not_found(recipe_finder: RecipeFinder) -> None:
    """Test find_recipe method when the recipe is not found."""
    with pytest.raises(RecipeLookupException):
        await recipe_finder.find_recipe("NonExistentRecipe")


@pytest.mark.asyncio
async def test_find_recipe_prefers_override(
    recipe_finder: RecipeFinder, tmp_path: Path
) -> None:
    """Test that the override directory is preferred over the search directory."""
    override_recipe = tmp_path / "override" / "MyRecipe.recipe"
    search_recipe = tmp_path / "search" / "MyRecipe.recipe"

    tmp_path.joinpath("override").mkdir(parents=True)
    tmp_path.joinpath("search").mkdir(parents=True)

    override_recipe.write_text("Override Recipe")
    search_recipe.write_text("Search Recipe")

    found_path = await recipe_finder.find_recipe("MyRecipe.recipe")
    assert found_path == override_recipe


@pytest.mark.asyncio
async def test_find_recipe_handles_tilde_expansion(
    recipe_finder: RecipeFinder, tmp_path: Path
) -> None:
    """Test that find_recipe correctly handles tilde expansion in paths."""
    tilde_path = str(tmp_path).replace(str(Path.home()), "~")
    recipe_file = tmp_path / "override" / "MyRecipe.recipe"

    mock_prefs = MagicMock()
    mock_prefs.recipe_override_dirs = [Path(tilde_path) / "override"]
    mock_prefs.recipe_search_dirs = [Path(tilde_path) / "search"]

    with patch(
        "cloud_autopkg_runner.recipe_finder.AutoPkgPrefs", return_value=mock_prefs
    ):
        recipe_finder = RecipeFinder()
        recipe_finder.logger = MagicMock()  # Mock the logger to avoid actual logging

        tmp_path.joinpath("override").mkdir(parents=True)
        recipe_file.write_text("Recipe content")

        found_path = await recipe_finder.find_recipe("MyRecipe.recipe")
        assert found_path == recipe_file


@pytest.mark.asyncio
async def test_find_recipe_custom_recursion_depth(tmp_path: Path) -> None:
    """Test find_recipe with a custom recursion depth."""
    mock_prefs = MagicMock()
    mock_prefs.recipe_override_dirs = [tmp_path / "override"]
    mock_prefs.recipe_search_dirs = [tmp_path / "search"]

    with patch(
        "cloud_autopkg_runner.recipe_finder.AutoPkgPrefs", return_value=mock_prefs
    ):
        recipe_finder = RecipeFinder(max_recursion_depth=1)
        recipe_finder.logger = MagicMock()

        search_dir = tmp_path / "search"
        search_dir.mkdir(parents=True, exist_ok=True)
        (search_dir / "subdir").mkdir(exist_ok=True)
        target_file = search_dir / "subdir" / "MyRecipe.recipe"
        target_file.write_text("Recipe content")

        with pytest.raises(RecipeLookupException):
            await recipe_finder.find_recipe("MyRecipe.recipe")

        recipe_finder = RecipeFinder(max_recursion_depth=2)
        recipe_finder.logger = MagicMock()
        found_path = await recipe_finder.find_recipe("MyRecipe.recipe")
        assert found_path == target_file
