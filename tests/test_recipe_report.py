import plistlib
from pathlib import Path
from typing import Any

import pytest

from cloud_autopkg_runner import recipe_report
from cloud_autopkg_runner.exceptions import InvalidPlistContents


def create_dummy_file(content: str, path: Path) -> None:
    """Creates a dummy file for testing."""
    path.write_text(content)


def create_dummy_plist(content: dict[str, Any], path: Path) -> None:
    """Creates a dummy plist file for testing."""
    path.write_bytes(plistlib.dumps(content))


def test_recipe_report_init(tmp_path: Path) -> None:
    """Test initializing a RecipeReport object."""
    report_path = tmp_path / "report.plist"
    report = recipe_report.RecipeReport(report_path)

    assert report.file_path() == report_path


def test_recipe_report_refresh_contents(tmp_path: Path) -> None:
    """Test parsing a valid report file."""
    report_path = tmp_path / "report.plist"
    report = recipe_report.RecipeReport(report_path)
    content: dict[str, Any] = {
        "failures": [],
        "summary_results": {
            "url_downloader_summary_result": {
                "data_rows": [{"file_path": "path/to/downloaded/file"}],
                "header": [],
                "summary_text": "",
            }
        },
    }
    create_dummy_plist(content, report_path)

    report.refresh_contents()

    assert isinstance(report.contents, dict)
    assert report.failures == content["failures"]
    assert report.summary_results == content["summary_results"]


def test_recipe_report_refresh_contents_invalid_plist(tmp_path: Path) -> None:
    """Test parsing an invalid report file raises the appropriate exception."""
    report_path = tmp_path / "report.plist"
    create_dummy_file("invalid plist content", report_path)
    report = recipe_report.RecipeReport(report_path)

    with pytest.raises(InvalidPlistContents):
        report.refresh_contents()


def test_recipe_report_consolidate_report(tmp_path: Path) -> None:
    """Test consolidation is doing what's expected."""
    report_path = tmp_path / "test.plist"
    content = {
        "failures": [
            {"message": "message", "recipe": "recipe", "traceback": "traceback"}
        ],
        "summary_results": {
            "url_downloader_summary_result": {
                "data_rows": [
                    {"url": "http://example.com/test"},
                    {"url": "http://example.com/test2"},
                ],
                "header": [],
                "summary_text": "text",
            },
            "pkg_summary_result": {
                "data_rows": [{"pkg": "text"}, {"pkg": "text"}],
                "header": [],
                "summary_text": "text",
            },
            "munki_importer_summary_result": {
                "data_rows": [{"imported": "here"}, {"imported": "here"}],
                "header": [],
                "summary_text": "text",
            },
        },
    }

    create_dummy_plist(content, report_path)

    report = recipe_report.RecipeReport(report_path)
    report.refresh_contents()

    consolidated = report.consolidate_report()

    assert consolidated == {
        "failed_items": [
            {"message": "message", "recipe": "recipe", "traceback": "traceback"}
        ],
        "downloaded_items": [
            {"url": "http://example.com/test"},
            {"url": "http://example.com/test2"},
        ],
        "pkg_built_items": [{"pkg": "text"}, {"pkg": "text"}],
        "munki_imported_items": [{"imported": "here"}, {"imported": "here"}],
    }
