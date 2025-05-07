import plistlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cloud_autopkg_runner import AutoPkgPrefs, Recipe
from cloud_autopkg_runner.exceptions import (
    InvalidFileContents,
    RecipeFormatException,
    RecipeInputException,
)
from cloud_autopkg_runner.recipe import RecipeContents, RecipeFormat


def create_dummy_file(path: Path, content: str) -> None:
    """Creates a dummy file for testing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


@pytest.fixture
def mock_autopkg_prefs(tmp_path: Path) -> MagicMock:
    """Fixture to create a mock AutoPkgPrefs object with search/override dirs.

    Returns:
        MagicMock: A mock AutoPkgPrefs object.
    """
    mock_prefs = MagicMock(spec=AutoPkgPrefs)
    mock_prefs.recipe_override_dirs = [tmp_path]
    mock_prefs.recipe_search_dirs = [tmp_path]
    return mock_prefs


def test_recipe_init_yaml(tmp_path: Path, mock_autopkg_prefs: MagicMock) -> None:
    """Test initializing a Recipe object from a YAML file."""
    yaml_content = """
    Description: Test recipe
    Identifier: com.example.test
    Input:
        NAME: TestRecipe
    Process: []
    """
    recipe_file = tmp_path / "Test.recipe.yaml"
    create_dummy_file(recipe_file, yaml_content)
    report_dir = tmp_path / "report_dir"
    report_dir.mkdir()

    with patch(
        "cloud_autopkg_runner.recipe_finder.AutoPkgPrefs",
        return_value=mock_autopkg_prefs,
    ):
        recipe = Recipe(recipe_file, report_dir)

    assert recipe.identifier == "com.example.test"
    assert recipe.input_name == "TestRecipe"
    assert recipe.format() == RecipeFormat.YAML
    assert recipe._result.file_path().parent == report_dir


def test_recipe_init_plist(tmp_path: Path, mock_autopkg_prefs: MagicMock) -> None:
    """Test initializing a Recipe object from a plist file."""
    plist_content: RecipeContents = {
        "Description": "Test recipe",
        "Identifier": "com.example.test",
        "Input": {"NAME": "TestRecipe"},
        "Process": [],
        "MinimumVersion": "",
        "ParentRecipe": "",
    }
    recipe_file = tmp_path / "Test.recipe.plist"
    recipe_file.write_bytes(plistlib.dumps(plist_content))

    with patch(
        "cloud_autopkg_runner.recipe_finder.AutoPkgPrefs",
        return_value=mock_autopkg_prefs,
    ):
        report_dir = tmp_path / "report_dir"
        report_dir.mkdir()
        recipe = Recipe(recipe_file, report_dir)
        assert recipe.identifier == "com.example.test"
        assert recipe.input_name == "TestRecipe"
        assert recipe.format() == RecipeFormat.PLIST
        assert recipe._result.file_path().parent == report_dir


def test_recipe_invalid_format(tmp_path: Path, mock_autopkg_prefs: MagicMock) -> None:
    """Test initializing a Recipe object with an invalid file format."""
    plist_content: RecipeContents = {
        "Description": "Test recipe",
        "Identifier": "com.example.test",
        "Input": {"NAME": "TestRecipe"},
        "Process": [],
        "MinimumVersion": "",
        "ParentRecipe": "",
    }
    recipe_file = tmp_path / "Test.recipe.invalid"
    recipe_file.write_bytes(plistlib.dumps(plist_content))

    report_dir = tmp_path / "report_dir"
    report_dir.mkdir()

    with (
        patch(
            "cloud_autopkg_runner.recipe_finder.AutoPkgPrefs",
            return_value=mock_autopkg_prefs,
        ),
        patch(
            "cloud_autopkg_runner.recipe_finder.RecipeFinder.find_recipe",
            return_value=recipe_file,
        ),
        pytest.raises(RecipeFormatException),
    ):
        Recipe(recipe_file, report_dir)


def test_recipe_invalid_content(tmp_path: Path, mock_autopkg_prefs: MagicMock) -> None:
    """Test initializing a Recipe object with an invalid file format."""
    recipe_file = tmp_path / "Test.recipe"
    create_dummy_file(recipe_file, "invalid content")
    report_dir = tmp_path / "report_dir"
    report_dir.mkdir()

    with (
        patch(
            "cloud_autopkg_runner.recipe_finder.AutoPkgPrefs",
            return_value=mock_autopkg_prefs,
        ),
        pytest.raises(InvalidFileContents),
    ):
        Recipe(recipe_file, report_dir)


def test_recipe_missing_name(tmp_path: Path, mock_autopkg_prefs: MagicMock) -> None:
    """Test initializing a Recipe object with missing NAME input."""
    yaml_content = """
    Description: Test recipe
    Identifier: com.example.test
    Input: {}
    Process: []
    """
    recipe_file = tmp_path / "Test.recipe.yaml"
    create_dummy_file(recipe_file, yaml_content)
    report_dir = tmp_path / "report_dir"
    report_dir.mkdir()

    with patch(
        "cloud_autopkg_runner.recipe_finder.AutoPkgPrefs",
        return_value=mock_autopkg_prefs,
    ):
        recipe = Recipe(recipe_file, report_dir)
        with pytest.raises(RecipeInputException):
            _ = recipe.input_name


def test_recipe_properties(tmp_path: Path, mock_autopkg_prefs: MagicMock) -> None:
    """Tests the various property accessors of the Recipe class."""
    yaml_content = """
    Description: Test recipe
    Identifier: com.example.test
    Input:
        NAME: TestRecipe
    Process: []
    MinimumVersion: 2.0
    ParentRecipe: ParentRecipe.recipe
    """
    recipe_file = tmp_path / "Test.recipe.yaml"
    create_dummy_file(recipe_file, yaml_content)
    report_dir = tmp_path / "report_dir"
    report_dir.mkdir()

    with patch(
        "cloud_autopkg_runner.recipe_finder.AutoPkgPrefs",
        return_value=mock_autopkg_prefs,
    ):
        recipe = Recipe(recipe_file, report_dir)

    assert recipe.contents["Description"] == "Test recipe"
    assert recipe.description == "Test recipe"
    assert recipe.identifier == "com.example.test"
    assert recipe.input_name == "TestRecipe"
    assert recipe.minimum_version == 2.0
    assert recipe.name == "Test.recipe.yaml"
    assert recipe.parent_recipe == "ParentRecipe.recipe"
    assert recipe.process == []


def test_autopkg_run_cmd_basic(tmp_path: Path, mock_autopkg_prefs: MagicMock) -> None:
    """Test basic command construction with no verbosity or processors."""
    yaml_content = """
    Description: Dummy
    Identifier: com.example.dummy
    Input:
        NAME: DummyRecipe
    Process: []
    """
    recipe_file = tmp_path / "Dummy.recipe.yaml"
    create_dummy_file(recipe_file, yaml_content)
    report_dir = tmp_path / "report"
    report_dir.mkdir()

    with (
        patch(
            "cloud_autopkg_runner.recipe_finder.AutoPkgPrefs",
            return_value=mock_autopkg_prefs,
        ),
        patch("cloud_autopkg_runner.recipe.Settings") as mock_settings,
    ):
        mock_settings.return_value.pre_processors = []
        mock_settings.return_value.post_processors = []
        mock_settings.return_value.verbosity_int.return_value = 0
        mock_settings.return_value.verbosity_str.return_value = ""

        recipe = Recipe(recipe_file, report_dir)
        cmd = recipe._autopkg_run_cmd()

        assert cmd[:3] == ["/usr/local/bin/autopkg", "run", recipe.name]
        assert any(arg.startswith("--report-plist=") for arg in cmd)
        assert "--check" not in cmd


def test_autopkg_run_cmd_with_check(
    tmp_path: Path, mock_autopkg_prefs: MagicMock
) -> None:
    """Test command includes --check when requested."""
    yaml_content = """
    Description: Dummy
    Identifier: com.example.dummy
    Input:
        NAME: DummyRecipe
    Process: []
    """
    recipe_file = tmp_path / "Dummy.recipe.yaml"
    create_dummy_file(recipe_file, yaml_content)
    report_dir = tmp_path / "report"
    report_dir.mkdir()

    with (
        patch(
            "cloud_autopkg_runner.recipe_finder.AutoPkgPrefs",
            return_value=mock_autopkg_prefs,
        ),
        patch("cloud_autopkg_runner.recipe.Settings") as mock_settings,
    ):
        mock_settings.return_value.pre_processors = []
        mock_settings.return_value.post_processors = []
        mock_settings.return_value.verbosity_int.return_value = 0
        mock_settings.return_value.verbosity_str.return_value = ""

        recipe = Recipe(recipe_file, report_dir)
        cmd = recipe._autopkg_run_cmd(check=True)

        assert "--check" in cmd


def test_autopkg_run_cmd_with_processors_and_verbosity(
    tmp_path: Path, mock_autopkg_prefs: MagicMock
) -> None:
    """Test command with pre/post processors and verbosity."""
    yaml_content = """
    Description: Dummy
    Identifier: com.example.dummy
    Input:
        NAME: DummyRecipe
    Process: []
    """
    recipe_file = tmp_path / "Dummy.recipe.yaml"
    create_dummy_file(recipe_file, yaml_content)
    report_dir = tmp_path / "report"
    report_dir.mkdir()

    with (
        patch(
            "cloud_autopkg_runner.recipe_finder.AutoPkgPrefs",
            return_value=mock_autopkg_prefs,
        ),
        patch("cloud_autopkg_runner.recipe.Settings") as mock_settings,
    ):
        mock_settings.return_value.pre_processors = [
            "PreA",
            "com.example.test/PreProcessorB",
        ]
        mock_settings.return_value.post_processors = ["PostA"]
        mock_settings.return_value.verbosity_int.return_value = 1
        mock_settings.return_value.verbosity_str.return_value = "-v"

        recipe = Recipe(recipe_file, report_dir)
        cmd = recipe._autopkg_run_cmd()

        assert "--preprocessor=PreA" in cmd
        assert "--preprocessor=com.example.test/PreProcessorB" in cmd
        assert cmd.index("--preprocessor=PreA") < cmd.index(
            "--preprocessor=com.example.test/PreProcessorB"
        )
        assert "--postprocessor=PostA" in cmd
        assert "-v" in cmd
