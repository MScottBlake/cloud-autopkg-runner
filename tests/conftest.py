from collections.abc import Generator

import pytest

from cloud_autopkg_runner import AutoPkgPrefs, Settings


@pytest.fixture(autouse=True)
def reset_singletons() -> Generator[None, None, None]:
    """Fixture to reset the singleton instances before each test.

    This ensures that each test gets a clean, independent instance of each singleton,
    preventing test contamination.
    """
    yield
    AutoPkgPrefs._instance = None
    Settings._instance = None
