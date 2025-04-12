# Cloud AutoPkg Runner

[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![PyPI Version](https://img.shields.io/pypi/v/cloud-autopkg-runner)](https://pypi.org/project/cloud-autopkg-runner/)
[![codecov](https://codecov.io/gh/MScottBlake/cloud-autopkg-runner/graph/badge.svg?token=V61UNG93JE)](https://codecov.io/gh/MScottBlake/cloud-autopkg-runner)

## Description

Cloud AutoPkg Runner is a Python library designed to provide tools and utilities for managing [AutoPkg](https://github.com/autopkg/autopkg) recipes and workflows concurrently. It streamlines AutoPkg automation in CI/CD pipelines, offering enhanced performance and scalability.

The main goal of this project is to streamline CI/CD pipelines and similar environments where AutoPkg is run ephemerally. In these environments, a file that was downloaded previously, is usually not available on the next run. This causes unnecessary downloads of the same content over and over. The metadata cache feature stores relevent file attributes from each downloaded file so that it can construct fake files on subsequent runs. Not only does this feature reduce the amount of downloaded material, it significantly decreases runtime.

As the name implies, Cloud AutoPkg Runner is designed to make integration in cloud environments like hosted runners seamless, but you don't need to be running in the cloud. You can just as easily run a LaunchDaemon on a Mac Mini that sits in a closet. It is versatile enough that tou can run as a CLI or as a Python library import, whatever fits your workflow.

:memo: Note: Example workflows will be showcased in [cloud-autopkg-runner-examples](https://github.com/MScottBlake/cloud-autopkg-runner-examples) but this is currently a Work in Progress.

## Features

* **Concurrent Recipe Processing:** Run AutoPkg recipes concurrently for faster execution.
* **Metadata Caching:** Improves efficiency by caching metadata from downloads and reducing redundant subsequent downloading of the same file.
* **Robust Error Handling:** Comprehensive exception handling and logging for reliable automation.
* **Flexible Configuration:** Easily configure the library using command-line arguments.
* **Cloud-Friendly:** Designed for seamless integration with CI/CD systems, even on hosted runners.

## Installation

### Prerequisites

* Python 3.10 or higher
* [AutoPkg](https://github.com/autopkg/autopkg) installed and configured

### Installing with uv

```bash
uv add cloud-autopkg-runner
```

### Installing with pip

```bash
python -m pip install cloud-autopkg-runner
```

## Usage

### Command Line

The cloud-autopkg-runner library provides a command-line interface (CLI) for running AutoPkg recipes. [uv](https://docs.astral.sh/uv/) is recommended (`uv run autopkg-run`), but you can also call it from the command line as a Python module (`python -m cloud_autopkg_runner`) or as a Python import (`import cloud_autopkg_runner`).

Future examples will assume you are running it with `uv`.

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
import logging
from pathlib import Path

from cloud_autopkg_runner.file_utils import create_dummy_files
from cloud_autopkg_runner.metadata_cache import MetadataCacheManager
from cloud_autopkg_runner.recipe import Recipe


async def main() -> None:
    logger = logging.getLogger(__name__)

    metatada_cache_path = Path("/path/to/metadata_cache.json")
    metadata_cache = await MetadataCacheManager.load(metatada_cache_path)

    recipe_list_path = Path("/path/to/recipe_list.json")
    recipe_list = json.loads(recipe_list_path.read_text())

    await create_dummy_files(recipe_list, metadata_cache)

    for recipe_name in recipe_list:
        logger.info("Processing %s", recipe_name)
        recipe = Recipe(recipe_name)

        if await recipe.verify_trust_info():
            await recipe.run()
            # Code to Commit changes here
        else:
            await recipe.update_trust_info()
            # Code to Open a PR here


if __name__ == "__main__":
    asyncio.run(main())
```

## Contributing

Contributions are welcome! Please refer to the `CONTRIBUTING.md` file for guidelines.

## License

This project is licensed under the MIT License - see the `LICENSE` file for details.

## Acknowledgments

[AutoPkg](https://github.com/autopkg/autopkg)
