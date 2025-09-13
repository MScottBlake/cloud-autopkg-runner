import errno
import plistlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cloud_autopkg_runner import AutoPkgPrefs, Recipe
from cloud_autopkg_runner.exceptions import (
    InvalidFileContents,
    RecipeFormatException,
    RecipeInputException,
)
from cloud_autopkg_runner.recipe import RecipeContents, RecipeFormat


def create_test_file(path: Path, content: str) -> None:
    """Creates a file for testing."""
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
    create_test_file(recipe_file, yaml_content)
    report_dir = tmp_path / "report_dir"
    report_dir.mkdir()

    recipe = Recipe(recipe_file, report_dir, mock_autopkg_prefs)

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

    report_dir = tmp_path / "report_dir"
    report_dir.mkdir()
    recipe = Recipe(recipe_file, report_dir, mock_autopkg_prefs)
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
            "cloud_autopkg_runner.recipe_finder.RecipeFinder.find_recipe",
            return_value=recipe_file,
        ),
        pytest.raises(RecipeFormatException),
    ):
        Recipe(recipe_file, report_dir, mock_autopkg_prefs)


def test_recipe_invalid_content(tmp_path: Path, mock_autopkg_prefs: MagicMock) -> None:
    """Test initializing a Recipe object with an invalid file format."""
    recipe_file = tmp_path / "Test.recipe"
    create_test_file(recipe_file, "invalid content")
    report_dir = tmp_path / "report_dir"
    report_dir.mkdir()

    with pytest.raises(InvalidFileContents):
        Recipe(recipe_file, report_dir, mock_autopkg_prefs)


def test_recipe_missing_name(tmp_path: Path, mock_autopkg_prefs: MagicMock) -> None:
    """Test initializing a Recipe object with missing NAME input."""
    yaml_content = """
    Description: Test recipe
    Identifier: com.example.test
    Input: {}
    Process: []
    """
    recipe_file = tmp_path / "Test.recipe.yaml"
    create_test_file(recipe_file, yaml_content)
    report_dir = tmp_path / "report_dir"
    report_dir.mkdir()

    recipe = Recipe(recipe_file, report_dir, mock_autopkg_prefs)
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
    create_test_file(recipe_file, yaml_content)
    report_dir = tmp_path / "report_dir"
    report_dir.mkdir()

    recipe = Recipe(recipe_file, report_dir, mock_autopkg_prefs)

    assert recipe.contents["Description"] == "Test recipe"
    assert recipe.description == "Test recipe"
    assert recipe.identifier == "com.example.test"
    assert recipe.input_name == "TestRecipe"
    assert recipe.minimum_version == 2.0
    assert recipe.name == "Test.recipe.yaml"
    assert recipe.parent_recipe == "ParentRecipe.recipe"
    assert recipe.process == []


@pytest.mark.asyncio
async def test_autopkg_run_cmd_basic(
    tmp_path: Path, mock_autopkg_prefs: MagicMock
) -> None:
    """Test basic command construction with no verbosity or processors."""
    yaml_content = """
    Description: Test
    Identifier: com.example.test
    Input:
        NAME: TestRecipe
    Process: []
    """
    recipe_file = tmp_path / "test.recipe.yaml"
    create_test_file(recipe_file, yaml_content)
    report_dir = tmp_path / "report"
    report_dir.mkdir()

    with patch("cloud_autopkg_runner.recipe.Settings") as mock_settings:
        mock_settings.return_value.pre_processors = []
        mock_settings.return_value.post_processors = []
        mock_settings.return_value.verbosity_int.return_value = 0
        mock_settings.return_value.verbosity_str.return_value = ""

        recipe = Recipe(recipe_file, report_dir, mock_autopkg_prefs)
        cmd = await recipe._autopkg_run_cmd()

        assert cmd[:3] == ["/usr/local/bin/autopkg", "run", recipe.name]
        assert any(arg.startswith("--report-plist=") for arg in cmd)
        assert "--check" not in cmd


@pytest.mark.asyncio
async def test_autopkg_run_cmd_with_check(
    tmp_path: Path, mock_autopkg_prefs: MagicMock
) -> None:
    """Test command includes --check when requested."""
    yaml_content = """
    Description: Test
    Identifier: com.example.test
    Input:
        NAME: TestRecipe
    Process: []
    """
    recipe_file = tmp_path / "test.recipe.yaml"
    create_test_file(recipe_file, yaml_content)
    report_dir = tmp_path / "report"
    report_dir.mkdir()

    with patch("cloud_autopkg_runner.recipe.Settings") as mock_settings:
        mock_settings.return_value.pre_processors = []
        mock_settings.return_value.post_processors = []
        mock_settings.return_value.verbosity_int.return_value = 0
        mock_settings.return_value.verbosity_str.return_value = ""

        recipe = Recipe(recipe_file, report_dir, mock_autopkg_prefs)
        cmd = await recipe._autopkg_run_cmd(check=True)

        assert "--check" in cmd


@pytest.mark.asyncio
async def test_autopkg_run_cmd_with_processors_and_verbosity(
    tmp_path: Path, mock_autopkg_prefs: MagicMock
) -> None:
    """Test command with pre/post processors and verbosity."""
    yaml_content = """
    Description: Test
    Identifier: com.example.test
    Input:
        NAME: TestRecipe
    Process: []
    """
    recipe_file = tmp_path / "test.recipe.yaml"
    create_test_file(recipe_file, yaml_content)
    report_dir = tmp_path / "report"
    report_dir.mkdir()

    with patch("cloud_autopkg_runner.recipe.Settings") as mock_settings:
        mock_settings.return_value.pre_processors = [
            "PreA",
            "com.example.test/PreProcessorB",
        ]
        mock_settings.return_value.post_processors = ["PostA"]
        mock_settings.return_value.verbosity_int.return_value = 1
        mock_settings.return_value.verbosity_str.return_value = "-v"

        recipe = Recipe(recipe_file, report_dir, mock_autopkg_prefs)
        cmd = await recipe._autopkg_run_cmd()

        assert "--preprocessor=PreA" in cmd
        assert "--preprocessor=com.example.test/PreProcessorB" in cmd
        assert cmd.index("--preprocessor=PreA") < cmd.index(
            "--preprocessor=com.example.test/PreProcessorB"
        )
        assert "--postprocessor=PostA" in cmd
        assert "-v" in cmd


@pytest.mark.asyncio
async def test_create_placeholder_cache_files_first_run(
    tmp_path: Path, mock_autopkg_prefs: MagicMock
) -> None:
    """Test that file_utils is called and the flag is set on the first run."""
    recipe_file = tmp_path / "Test.recipe.yaml"
    recipe_file.write_text("""
    Description: Test
    Identifier: com.example.test
    Input:
        NAME: TestRecipe
    Process: []
    """)

    with (
        patch(
            "cloud_autopkg_runner.file_utils.create_placeholder_files",
            new_callable=AsyncMock,
        ) as mock_create_placeholder_files,
        patch("cloud_autopkg_runner.recipe.Settings"),
    ):
        recipe = Recipe(recipe_file, tmp_path, mock_autopkg_prefs)
        # Ensure the flag is not set initially
        assert not hasattr(recipe, "_placeholder_files_created")

        await recipe._create_placeholder_cache_files()

        mock_create_placeholder_files.assert_called_once_with([recipe.name])
        assert recipe._placeholder_files_created is True


@pytest.mark.asyncio
async def test_create_placeholder_cache_files_subsequent_run(
    tmp_path: Path, mock_autopkg_prefs: MagicMock
) -> None:
    """Test that file_utils is not called a second time."""
    recipe_file = tmp_path / "Test.recipe.yaml"
    recipe_file.write_text("""
    Description: Test
    Identifier: com.example.test
    Input:
        NAME: TestRecipe
    Process: []
    """)

    with (
        patch(
            "cloud_autopkg_runner.file_utils.create_placeholder_files",
            new_callable=AsyncMock,
        ) as mock_create_placeholder_files,
        patch("cloud_autopkg_runner.recipe.Settings"),
    ):
        recipe = Recipe(recipe_file, tmp_path, mock_autopkg_prefs)
        # Manually set the flag to simulate a previous run
        recipe._placeholder_files_created = True

        await recipe._create_placeholder_cache_files()

        mock_create_placeholder_files.assert_not_called()


@pytest.mark.asyncio
async def test_get_metadata_for_item_all_present() -> None:
    """Test _get_metadata_for_item when all metadata is present."""
    test_file_path_str = "/tmp/test_downloaded_file.dmg"
    test_file_path = Path(test_file_path_str)
    expected_etag = "a1b2c3d4e5f6g7h8i9j0"
    expected_file_size = 123456789
    expected_last_modified = "Tue, 1 Jan 2024 12:00:00 GMT"

    # Patch the utility functions that _get_metadata_for_item calls
    with (
        patch(
            "cloud_autopkg_runner.file_utils.get_file_size", new_callable=AsyncMock
        ) as mock_get_file_size,
        patch(
            "cloud_autopkg_runner.file_utils.get_file_metadata", new_callable=AsyncMock
        ) as mock_get_file_metadata,
    ):
        mock_get_file_size.return_value = expected_file_size
        # Configure get_file_metadata for specific attributes
        mock_get_file_metadata.side_effect = [
            expected_etag,  # for "com.github.autopkg.etag"
            expected_last_modified,  # for "com.github.autopkg.last-modified"
        ]

        result = await Recipe._get_metadata_for_item(test_file_path_str)

        # Assertions for the mock calls
        mock_get_file_size.assert_called_once_with(test_file_path)
        assert mock_get_file_metadata.call_count == 2
        mock_get_file_metadata.assert_any_call(
            test_file_path, "com.github.autopkg.etag"
        )
        mock_get_file_metadata.assert_any_call(
            test_file_path, "com.github.autopkg.last-modified"
        )

        # Assertions for the returned DownloadMetadata
        assert result == {
            "file_path": test_file_path_str,
            "file_size": expected_file_size,
            "etag": expected_etag,
            "last_modified": expected_last_modified,
        }


@pytest.mark.asyncio
async def test_get_metadata_for_item_missing_optional_metadata() -> None:
    """Test _get_metadata_for_item when etag and last_modified are missing."""
    test_file_path_str = "/tmp/test_downloaded_file.dmg"
    test_file_path = Path(test_file_path_str)
    expected_file_size = 987654321

    with (
        patch(
            "cloud_autopkg_runner.file_utils.get_file_size", new_callable=AsyncMock
        ) as mock_get_file_size,
        patch(
            "cloud_autopkg_runner.file_utils.get_file_metadata", new_callable=AsyncMock
        ) as mock_get_file_metadata,
    ):
        mock_get_file_size.return_value = expected_file_size
        # Simulate missing metadata by returning None
        mock_get_file_metadata.side_effect = [
            None,  # for "com.github.autopkg.etag"
            None,  # for "com.github.autopkg.last-modified"
        ]

        result = await Recipe._get_metadata_for_item(test_file_path_str)

        mock_get_file_size.assert_called_once_with(test_file_path)
        assert mock_get_file_metadata.call_count == 2
        mock_get_file_metadata.assert_any_call(
            test_file_path, "com.github.autopkg.etag"
        )
        mock_get_file_metadata.assert_any_call(
            test_file_path, "com.github.autopkg.last-modified"
        )

        # Ensure only file_path and file_size are present
        assert result == {
            "file_path": test_file_path_str,
            "file_size": expected_file_size,
        }
        assert "etag" not in result
        assert "last_modified" not in result


@pytest.mark.asyncio
async def test_get_metadata_for_item_file_size_error() -> None:
    """Test _get_metadata_for_item when get_file_size raises an OSError."""
    test_file_path_str = "/tmp/test_downloaded_file.dmg"
    test_file_path = Path(test_file_path_str)
    # Use EIO for a generic OSError that should cause the function to raise
    expected_error = OSError(errno.EIO, "Input/output error")

    with patch(
        "cloud_autopkg_runner.file_utils.get_file_size", new_callable=AsyncMock
    ) as mock_get_file_size:
        mock_get_file_size.side_effect = expected_error

        with pytest.raises(OSError) as exc_info:  # noqa: PT011
            await Recipe._get_metadata_for_item(test_file_path_str)

        assert exc_info.type is OSError
        assert exc_info.value.errno == expected_error.errno
        mock_get_file_size.assert_called_once_with(test_file_path)


@pytest.mark.asyncio
async def test_get_metadata_for_item_etag_error() -> None:
    """Test _get_metadata_for_item when etag retrieval raises an OSError."""
    test_file_path_str = "/tmp/test_downloaded_file.dmg"
    test_file_path = Path(test_file_path_str)
    expected_file_size = 12345
    expected_error = OSError(errno.EIO, "Etag read error")

    with (
        patch(
            "cloud_autopkg_runner.file_utils.get_file_size", new_callable=AsyncMock
        ) as mock_get_file_size,
        patch(
            "cloud_autopkg_runner.file_utils.get_file_metadata", new_callable=AsyncMock
        ) as mock_get_file_metadata,
    ):
        mock_get_file_size.return_value = expected_file_size
        # Configure get_file_metadata to raise for etag
        mock_get_file_metadata.side_effect = [
            expected_error,  # for "com.github.autopkg.etag"
            "some_last_modified",  # for "com.github.autopkg.last-modified"
        ]

        with pytest.raises(OSError) as exc_info:  # noqa: PT011
            await Recipe._get_metadata_for_item(test_file_path_str)

        assert exc_info.type is OSError
        assert exc_info.value.errno == expected_error.errno
        mock_get_file_size.assert_called_once_with(test_file_path)
        mock_get_file_metadata.assert_any_call(
            test_file_path, "com.github.autopkg.etag"
        )


@pytest.mark.asyncio
async def test_get_metadata_for_item_last_modified_error() -> None:
    """Test _get_metadata_for_item when last_modified retrieval raises an OSError."""
    test_file_path_str = "/tmp/test_downloaded_file.dmg"
    test_file_path = Path(test_file_path_str)
    expected_file_size = 12345
    expected_etag = "a1b2c3d4e5f6"
    expected_error = OSError(errno.EIO, "Last modified read error")

    with (
        patch(
            "cloud_autopkg_runner.file_utils.get_file_size", new_callable=AsyncMock
        ) as mock_get_file_size,
        patch(
            "cloud_autopkg_runner.file_utils.get_file_metadata", new_callable=AsyncMock
        ) as mock_get_file_metadata,
    ):
        mock_get_file_size.return_value = expected_file_size
        mock_get_file_metadata.side_effect = [
            expected_etag,  # for "com.github.autopkg.etag"
            expected_error,  # for "com.github.autopkg.last-modified"
        ]

        with pytest.raises(OSError) as exc_info:  # noqa: PT011
            await Recipe._get_metadata_for_item(test_file_path_str)

        assert exc_info.type is OSError
        assert exc_info.value.errno == expected_error.errno
        mock_get_file_size.assert_called_once_with(test_file_path)
        mock_get_file_metadata.assert_any_call(
            test_file_path, "com.github.autopkg.etag"
        )
        mock_get_file_metadata.assert_any_call(
            test_file_path, "com.github.autopkg.last-modified"
        )
