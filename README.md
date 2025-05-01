# Cloud AutoPkg Runner

A Python library designed to level-up your AutoPkg automations with a focus on CI/CD performance.

[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE.md)
[![PyPI Version](https://img.shields.io/pypi/v/cloud-autopkg-runner)](https://pypi.org/project/cloud-autopkg-runner/)
[![PyPI Downloads](https://static.pepy.tech/badge/cloud-autopkg-runner)](https://pepy.tech/projects/cloud-autopkg-runner)
[![CodeCov](https://codecov.io/gh/MScottBlake/cloud-autopkg-runner/graph/badge.svg?token=V61UNG93JE)](https://codecov.io/gh/MScottBlake/cloud-autopkg-runner)

![AutoPkgRunner](https://raw.githubusercontent.com/MScottBlake/cloud-autopkg-runner/main/docs/AutoPkgRunner.png)

## Description

Cloud AutoPkg Runner is a Python library designed to provide tools and utilities for managing [AutoPkg](https://github.com/autopkg/autopkg) recipes and workflows concurrently. It streamlines AutoPkg automation in CI/CD pipelines, offering enhanced performance and scalability.

The main goal of this project is to streamline CI/CD pipelines and similar environments where AutoPkg is run ephemerally. In these environments, a file that was downloaded previously, is usually not available on the next run. This causes unnecessary downloads of the same content over and over. The metadata cache feature stores relevent file attributes from each downloaded file so that it can construct fake files on subsequent runs. Not only does this feature reduce the amount of downloaded material, it significantly decreases runtime.

As the name implies, Cloud AutoPkg Runner is designed to make integration in cloud environments like hosted runners seamless, but you don't need to be running in the cloud. You can just as easily run a LaunchDaemon on a Mac Mini that sits in a closet. It is versatile enough that you can run as a CLI or as a Python library import, whatever fits your workflow.

:memo: Note: Example workflows will be showcased in [cloud-autopkg-runner-examples](https://github.com/MScottBlake/cloud-autopkg-runner-examples) but this is currently a Work in Progress.

## Features

* **Concurrent Recipe Processing:** Run AutoPkg recipes concurrently for faster execution.
* **Metadata Caching:** Improves efficiency by caching metadata from downloads and reducing redundant subsequent downloading of the same file.
* **Robust Error Handling:** Comprehensive exception handling and logging for reliable automation.
* **Flexible Configuration:** Easily configure the library using command-line arguments.
* **Cloud-Friendly:** Designed for seamless integration with CI/CD systems, even on hosted runners.

## Installation

Installation instructions are found on the [Installation](https://github.com/MScottBlake/cloud-autopkg-runner/wiki/Installation) page of the Wiki.

## Usage

See the [Wiki](https://github.com/MScottBlake/cloud-autopkg-runner/wiki) for usage information and more!

## Contributing

Contributions are welcome! Please refer to the `CONTRIBUTING.md` file for guidelines.

## License

This project is licensed under the MIT License - see the `LICENSE.md` file for details.
