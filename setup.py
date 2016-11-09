#!/usr/bin/env python

from distutils.core import setup

setup(
    name='Mesh Client',
    version='0.1.0',
    description='Client for NHS Digital \'s MESH messaging system',
    author='Greg Ward',
    author_email='gward@python.net',
    url='https://www.python.org/sigs/distutils-sig/',
    packages=['mesh_client'],
    package_data={'mesh_client': ['*.pem']},
    requires=[
        'requests (>=2.9.0)',
        'six (>=1.10.0)'
    ])
