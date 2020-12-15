#!/usr/bin/env python
from setuptools import setup
from os.path import dirname, join

with open(join(dirname(__file__), 'README.md')) as f:
    long_description = f.read()

setup(
    name='Mesh Client',
    description='Client for NHS Digital \'s MESH messaging system',
    url='https://github.com/jamespic/mesh-client',
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
    use_scm_version=True,
    setup_requires=['setuptools_scm'],
    entry_points={
        'console_scripts': [
            'mesh_auth=mesh_client.mesh_auth:main',
            'mock_mesh_server=mesh_client.mock_server:main'
        ]
    },
    license='MIT',
    python_requires='>=2.7,!=3.0.*,!=3.1.*,!=3.2.*,!=3.3.*',
    classifiers=[
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9'
    ]
)
