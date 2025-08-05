#!/usr/bin/env python
"""
this shim is required ... because the PyPI package name contains upper case chars . and pyproject.toml
will lowercase under PEP-518 build systems.
"""
import os
from os.path import dirname, join

import toml  # type: ignore[import]
from setuptools import setup, sic  # type: ignore[import]

with open(join(dirname(__file__), "pyproject.toml")) as f:
    pyproject = toml.loads(f.read())

poetry_cfg = pyproject["tool"]["poetry"]


with open(join(dirname(__file__), poetry_cfg["readme"])) as f:
    long_description = f.read()


def is_list_of_dicts_with_keys(value, keys):
    if isinstance(value, list):
        if all(isinstance(item, dict) and all(key in item for key in keys) for item in value):
            return True
        raise ValueError(
            "Dependency of type list must contain dictionaries "
            f"with keys {keys}."
            " See CONTRIBUTING.md for formatting"
        )
    return False


def format_installs_required(config):
    dependencies = []
    for k, v in config.items():
        if k == "python":
            continue
        elif is_list_of_dicts_with_keys(v, ["version", "markers"]):
            for package_version in v:
                version = package_version.get("version")
                markers = package_version.get("markers")
                dependencies.append(f"{k}{version} ; {markers}")
        else:
            dependencies.append(f"{k} ({v})")

    return dependencies


setup(
    name=poetry_cfg["name"],
    version=sic(os.environ.get("RELEASE_VERSION", poetry_cfg["version"])),
    description=poetry_cfg["description"],
    url=poetry_cfg["repository"],
    long_description=long_description,
    long_description_content_type="text/markdown",
    author=poetry_cfg["authors"][0],
    packages=["mesh_client"],
    package_data={"mesh_client": ["py.typed", "*.pem"]},
    install_requires=format_installs_required(poetry_cfg["dependencies"]),
    entry_points={
        "console_scripts": ["mesh_auth=mesh_client.mesh_auth:main", "mock_mesh_server=mesh_client.mock_server:main"]
    },
    license=poetry_cfg["license"],
    python_requires=poetry_cfg["dependencies"]["python"],
    classifiers=poetry_cfg.get("classifiers"),
)
