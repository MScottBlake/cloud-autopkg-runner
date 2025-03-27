# Cloud AutoPkg Runner

[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)  <!-- Replace LICENSE with your actual license file -->
[![PyPI Version](https://img.shields.io/pypi/v/cloud-autopkg-runner)](https://pypi.org/project/cloud-autopkg-runner/) <!-- Update on PyPI -->
[![Coverage Status](https://img.shields.io/codecov/c/github/<your_github_org>/cloud-autopkg-runner)](https://codecov.io/gh/<your_github_org>/cloud-autopkg-runner) <!-- Update with your Codecov repo -->

## Description

Cloud AutoPkg Runner is a Python library designed to provide asynchronous tools and utilities for managing [AutoPkg](https://github.com/autopkg/autopkg) recipes and workflows. It streamlines AutoPkg automation in cloud environments and CI/CD pipelines, offering enhanced performance and scalability.

This library provides modules for:

* Managing metadata caching
* Processing AutoPkg recipes asynchronously
* Executing shell commands with robust error handling
* Centralized configuration management

## Features

* **Asynchronous Recipe Processing:** Run AutoPkg recipes concurrently for faster execution.
* **Metadata Caching:** Improve efficiency by caching metadata and reducing redundant data fetching.
* **Robust Error Handling:** Comprehensive exception handling and logging for reliable automation.
* **Flexible Configuration:** Easily configure the library using command-line arguments and environment variables.
* **Cloud-Friendly:** Designed for seamless integration with cloud environments and CI/CD systems.

## Installation

### Prerequisites

* Python 3.10 or higher
* [AutoPkg](https://github.com/autopkg/autopkg) installed and configured

### Installing with uv

```bash
uv add cloud-autopkg-runer
```

### Installing from PyPI

```bash
pip install cloud-autopkg-runner
```

## Usage

### Command Line

The cloud-autopkg-runner library provides a command-line interface (CLI) for running AutoPkg recipes. UV is recommended (`uv run autopkg-run`), but you can also call it as a python module (`python -m cloud_autopkg_runner`).

### Running a Recipe

```bash
uv run autopkg-run --recipe Firefox.pkg.recipe
```

### Running Multiple Recipes

```bash
uv run autopkg-run --recipe Firefox.pkg.recipe --recipe GoogleChrome.pkg.recipe
```

### Specifying a Recipe List from a JSON File

Create a JSON file (`recipes.json`) containing a list of recipe names:

```json
[
    "Firefox.pkg.recipe",
    "GoogleChrome.pkg.recipe"
]
```

Then, run the recipes using the `--recipe-list` option:

```bash
uv run autopkg-run --recipe-list recipes.json
```

### Setting the Verbosity Level

Use the `-v` option to control the verbosity level. You can specify it multiple times for increased verbosity (e.g., `-vvv`).

```bash
uv run autopkg-run -vv --recipe Firefox.pkg.recipe
```

### Specifying a Log File

Use the `--log-file` option to specify a log file for the script's output:

```bash
uv run autopkg-run --log-file autopkg_runner.log --recipe Firefox.pkg.recipe
```

### As a Python Library

You can also use `cloud-autopkg-runner` as a Python library in your own scripts.

#### Example: Running recipes programmatically

```python
import asyncio
import json
from pathlib import Path

from cloud_autopkg_runner.metadata_cache import create_dummy_files, load_metadata_cache
from cloud_autopkg_runner.recipe import Recipe

async def main() -> None:
    metatada_cache_path = Path("/path/to/metadata_cache.json")
    metadata_cache = load_metadata_cache(metatada_cache_path)

    recipe_list_path = Path("/path/to/recipe_list.json")
    recipe_list = json.loads(recipe_list_path.read_text())

    create_dummy_files(recipe_list, metadata_cache)

    override_dir = Path("/path/to/autopkg/overrides")

    for recipe_name in recipe_list:
        recipe = Recipe(override_dir / recipe_name)

        if not await recipe.verify_trust_info():
            await recipe.run()
            # Commit changes
        else:
            await recipe.update_trust_info()
            # Open a PR


if __name__ == "__main__":
    asyncio.run(main())
```

## Contributing

Contributions are welcome! Please refer to the `CONTRIBUTING.md` file for guidelines.

## License

This project is licensed under the MIT License - see the `LICENSE` file for details.

## Acknowledgments

[AutoPkg](https://github.com/autopkg/autopkg)
