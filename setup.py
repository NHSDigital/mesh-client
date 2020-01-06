#!/usr/bin/env python
import setuptools
from distutils.core import setup

setup(
    name='Mesh Client',
    version='0.9.1',
    description='Client for NHS Digital \'s MESH messaging system',
    author='James Pickering',
    author_email='james.pickering@airelogic.com',
    packages=['mesh_client'],
    package_data={'mesh_client': ['*.pem']},
    install_requires=[
        'requests (>=2.9.0)',
        'six (>=1.10.0)'
    ])
