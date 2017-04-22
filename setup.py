#!/usr/bin/env python

from distutils.core import setup

setup(
    name='Mesh Client',
    version='0.7.1',
    description='Client for NHS Digital \'s MESH messaging system',
    author='James Pickering',
    author_email='james.pickering@xml-solutions.com',
    packages=['mesh_client'],
    package_data={'mesh_client': ['*.pem']},
    requires=[
        'requests (>=2.9.0)',
        'six (>=1.10.0)'
    ])
