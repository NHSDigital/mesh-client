#!/usr/bin/env python
"""
 this shim is required ... because the PyPI package name contains upper case chars . and pyproject.toml
 will lowercase under PEP-518 build systems.
"""
import os
from os.path import dirname, join

import toml  # type: ignore[import]
from setuptools import setup  # type: ignore[import]

with open(join(dirname(__file__), "pyproject.toml")) as f:
    pyproject = toml.loads(f.read())

poetry_cfg = pyproject["tool"]["poetry"]


with open(join(dirname(__file__), poetry_cfg["readme"])) as f:
    long_description = f.read()


setup(
    name=poetry_cfg["name"],
    version=os.environ.get("RELEASE_VERSION", poetry_cfg["version"]),
    description=poetry_cfg["description"],
    url=poetry_cfg["repository"],
    long_description=long_description,
    long_description_content_type="text/markdown",
    author=poetry_cfg["authors"][0],
    packages=["mesh_client"],
    package_data={"mesh_client": ["py.typed", "*.pem"]},
    install_requires=[f"{k} ({v})" for k, v in poetry_cfg["dependencies"].items() if k != "python"],
    entry_points={
        "console_scripts": ["mesh_auth=mesh_client.mesh_auth:main", "mock_mesh_server=mesh_client.mock_server:main"]
    },
    license=poetry_cfg["license"],
    python_requires=poetry_cfg["dependencies"]["python"],
    classifiers=poetry_cfg.get("classifiers"),
)
