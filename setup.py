#!/usr/bin/env python
import setuptools
from distutils.core import setup
from os.path import dirname, join

with open(join(dirname(__file__), 'README.md')) as f:
    long_description = f.read()

setup(
    name='Mesh Client',
    version='0.9.2',
    description='Client for NHS Digital \'s MESH messaging system',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='James Pickering',
    author_email='james.pickering@airelogic.com',
    packages=['mesh_client'],
    package_data={'mesh_client': ['*.pem']},
    install_requires=[
        'requests (>=2.9.0)',
        'six (>=1.10.0)'
    ],
    entry_points={
        'console_scripts': [
            'mesh_auth=mesh_client.mesh_auth:main',
            'mock_mesh_server=mesh_client.mock_server:main'
        ]
    },
    license='MIT',
    python_requires='>=2.7,!=3.0.*,!=3.1.*,!=3.2.*,!=3.3.*')
