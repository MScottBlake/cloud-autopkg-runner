import pytest

from cloud_autopkg_runner.common_utils import list_possible_file_names


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
def test_list_possible_file_names(recipe_name: str, expected_names: list[str]) -> None:
    """Tests list possible file names function based on naming structures.

    This test verifies that the list_possible_file_names function correctly
    generates the expected list of file names for various recipe names,
    including those with and without a file extension, using pytest's
    parameterization feature.
    """
    result = list_possible_file_names(recipe_name)
    assert result == expected_names
