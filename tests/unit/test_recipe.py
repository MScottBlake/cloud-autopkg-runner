import errno
import logging
import plistlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cloud_autopkg_runner import AutoPkgPrefs, Recipe, file_utils
from cloud_autopkg_runner.exceptions import (
    InvalidFileContentsError,
    RecipeFormatError,
    RecipeInputError,
)
from cloud_autopkg_runner.recipe import RecipeContents, RecipeFormat
from cloud_autopkg_runner.recipe_report import ConsolidatedReport


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
        pytest.raises(RecipeFormatError),
    ):
        Recipe(recipe_file, report_dir, mock_autopkg_prefs)


def test_recipe_invalid_content(tmp_path: Path, mock_autopkg_prefs: MagicMock) -> None:
    """Test initializing a Recipe object with an invalid file format."""
    recipe_file = tmp_path / "Test.recipe"
    create_test_file(recipe_file, "invalid content")
    report_dir = tmp_path / "report_dir"
    report_dir.mkdir()

    with pytest.raises(InvalidFileContentsError):
        Recipe(recipe_file, report_dir, mock_autopkg_prefs)


def test_recipe_malformed_xml(tmp_path: Path, mock_autopkg_prefs: MagicMock) -> None:
    """Truncated XML raises InvalidFileContentsError rather than ExpatError."""
    recipe_file = tmp_path / "Test.recipe"
    create_test_file(recipe_file, '<?xml version="1.0"?><plist version="1.0"><dict>')
    report_dir = tmp_path / "report_dir"
    report_dir.mkdir()

    with pytest.raises(InvalidFileContentsError):
        Recipe(recipe_file, report_dir, mock_autopkg_prefs)


def test_recipe_plist_not_a_mapping(
    tmp_path: Path, mock_autopkg_prefs: MagicMock
) -> None:
    """A valid plist that is not a mapping is rejected at load time."""
    recipe_file = tmp_path / "Test.recipe"
    create_test_file(
        recipe_file,
        '<?xml version="1.0"?><plist version="1.0"><string>nope</string></plist>',
    )
    report_dir = tmp_path / "report_dir"
    report_dir.mkdir()

    with pytest.raises(InvalidFileContentsError):
        Recipe(recipe_file, report_dir, mock_autopkg_prefs)


def test_recipe_yaml_not_a_mapping(
    tmp_path: Path, mock_autopkg_prefs: MagicMock
) -> None:
    """A valid YAML document that is not a mapping is rejected at load time."""
    recipe_file = tmp_path / "Test.recipe.yaml"
    create_test_file(recipe_file, "- just\n- a\n- list\n")
    report_dir = tmp_path / "report_dir"
    report_dir.mkdir()

    with pytest.raises(InvalidFileContentsError):
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
    with pytest.raises(RecipeInputError):
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
        assert not any(arg.startswith("--key=") for arg in cmd)


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
async def test_autopkg_run_cmd_with_input_variables(
    tmp_path: Path, mock_autopkg_prefs: MagicMock
) -> None:
    """Test command with input_variables."""
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
        mock_settings.return_value.input_variables = {
            "KEY1": "value1",
            "KEY2": "value2",
        }
        mock_settings.return_value.verbosity_int.return_value = 0
        mock_settings.return_value.verbosity_str.return_value = ""

        recipe = Recipe(recipe_file, report_dir, mock_autopkg_prefs)
        cmd = await recipe._autopkg_run_cmd()

        assert "--key=KEY1=value1" in cmd
        assert "--key=KEY2=value2" in cmd


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

        mock_create_placeholder_files.assert_called_once_with(
            [recipe.name], mock_autopkg_prefs
        )
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
            expected_etag,  # for the etag attribute
            expected_last_modified,  # for the last-modified attribute
        ]

        result = await Recipe._get_metadata_for_item(test_file_path_str)

        # Assertions for the mock calls
        mock_get_file_size.assert_called_once_with(test_file_path)
        assert mock_get_file_metadata.call_count == 2
        mock_get_file_metadata.assert_any_call(test_file_path, file_utils.XATTR_ETAG)
        mock_get_file_metadata.assert_any_call(
            test_file_path, file_utils.XATTR_LAST_MODIFIED
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
            None,  # for the etag attribute
            None,  # for the last-modified attribute
        ]

        result = await Recipe._get_metadata_for_item(test_file_path_str)

        mock_get_file_size.assert_called_once_with(test_file_path)
        assert mock_get_file_metadata.call_count == 2
        mock_get_file_metadata.assert_any_call(test_file_path, file_utils.XATTR_ETAG)
        mock_get_file_metadata.assert_any_call(
            test_file_path, file_utils.XATTR_LAST_MODIFIED
        )

        # Ensure only file_path and file_size are present
        assert result == {
            "file_path": test_file_path_str,
            "file_size": expected_file_size,
        }
        assert "etag" not in result
        assert "last_modified" not in result


@pytest.mark.asyncio
async def test_get_metadata_for_item_file_size_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An unreadable download is left uncached rather than failing the recipe."""
    test_file_path_str = "/tmp/test_downloaded_file.dmg"
    test_file_path = Path(test_file_path_str)
    expected_error = OSError(errno.EIO, "Input/output error")

    with patch(
        "cloud_autopkg_runner.file_utils.get_file_size", new_callable=AsyncMock
    ) as mock_get_file_size:
        mock_get_file_size.side_effect = expected_error

        with caplog.at_level(logging.WARNING):
            result = await Recipe._get_metadata_for_item(test_file_path_str)

        assert result is None
        assert "Could not read metadata" in caplog.text
        mock_get_file_size.assert_called_once_with(test_file_path)


@pytest.mark.asyncio
async def test_get_metadata_for_item_etag_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An etag read that raises leaves the item uncached, not the recipe failed.

    `get_file_metadata` reports an unreadable attribute as absent rather than
    raising, so this covers the belt-and-braces path.
    """
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
            expected_error,  # for the etag attribute
            "some_last_modified",  # for the last-modified attribute
        ]

        with caplog.at_level(logging.WARNING):
            result = await Recipe._get_metadata_for_item(test_file_path_str)

        assert result is None
        assert "Could not read metadata" in caplog.text
        mock_get_file_size.assert_called_once_with(test_file_path)
        mock_get_file_metadata.assert_any_call(test_file_path, file_utils.XATTR_ETAG)


@pytest.mark.asyncio
async def test_get_metadata_for_item_last_modified_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A last-modified read that raises leaves the item uncached."""
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
            expected_etag,  # for the etag attribute
            expected_error,  # for the last-modified attribute
        ]

        with caplog.at_level(logging.WARNING):
            result = await Recipe._get_metadata_for_item(test_file_path_str)

        assert result is None
        assert "Could not read metadata" in caplog.text
        mock_get_file_size.assert_called_once_with(test_file_path)
        mock_get_file_metadata.assert_any_call(test_file_path, file_utils.XATTR_ETAG)
        mock_get_file_metadata.assert_any_call(
            test_file_path, file_utils.XATTR_LAST_MODIFIED
        )


def _run_test_recipe(tmp_path: Path, mock_autopkg_prefs: MagicMock) -> Recipe:
    """Creates a minimal Recipe for exercising `run`.

    Returns:
        Recipe: A Recipe object backed by a throwaway YAML file.
    """
    recipe_file = tmp_path / "Test.recipe.yaml"
    create_test_file(
        recipe_file,
        """
    Description: Test
    Identifier: com.example.test
    Input:
        NAME: TestRecipe
    Process: []
    """,
    )
    return Recipe(recipe_file, tmp_path, mock_autopkg_prefs)


def _consolidated_report(*, failed: bool) -> ConsolidatedReport:
    """Builds a report with one downloaded item and optionally one failure.

    Returns:
        ConsolidatedReport: A report suitable for stubbing out a recipe run.
    """
    return ConsolidatedReport(
        failed_items=[{"recipe": "Test.recipe.yaml", "message": "boom"}]
        if failed
        else [],
        downloaded_items=[{"download_path": "/tmp/Test.dmg"}],
        pkg_built_items=[],
        munki_imported_items=[],
    )


@pytest.mark.asyncio
async def test_run_caches_metadata_after_successful_full_run(
    tmp_path: Path, mock_autopkg_prefs: MagicMock
) -> None:
    """Metadata is cached once the full run reports no failures."""
    mock_cache = AsyncMock()

    with (
        patch("cloud_autopkg_runner.recipe.Settings"),
        patch(
            "cloud_autopkg_runner.recipe.metadata_cache.get_cache_plugin",
            return_value=mock_cache,
        ),
    ):
        recipe = _run_test_recipe(tmp_path, mock_autopkg_prefs)
        recipe.run_check_phase = AsyncMock(  # type: ignore[method-assign]
            return_value=_consolidated_report(failed=False)
        )
        recipe.run_full = AsyncMock(  # type: ignore[method-assign]
            return_value=_consolidated_report(failed=False)
        )
        recipe._get_metadata = AsyncMock(return_value={})  # type: ignore[method-assign]

        report = await recipe.run()

        recipe.run_full.assert_awaited_once()
        mock_cache.set_item.assert_awaited_once()
        assert report["failed_items"] == []


@pytest.mark.asyncio
async def test_run_does_not_cache_metadata_after_failed_full_run(
    tmp_path: Path, mock_autopkg_prefs: MagicMock
) -> None:
    """A failed full run leaves the cache alone so the next run retries."""
    mock_cache = AsyncMock()

    with (
        patch("cloud_autopkg_runner.recipe.Settings"),
        patch(
            "cloud_autopkg_runner.recipe.metadata_cache.get_cache_plugin",
            return_value=mock_cache,
        ),
    ):
        recipe = _run_test_recipe(tmp_path, mock_autopkg_prefs)
        recipe.run_check_phase = AsyncMock(  # type: ignore[method-assign]
            return_value=_consolidated_report(failed=False)
        )
        recipe.run_full = AsyncMock(  # type: ignore[method-assign]
            return_value=_consolidated_report(failed=True)
        )
        recipe._get_metadata = AsyncMock(return_value={})  # type: ignore[method-assign]

        report = await recipe.run()

        recipe.run_full.assert_awaited_once()
        mock_cache.set_item.assert_not_awaited()
        assert report["failed_items"]
