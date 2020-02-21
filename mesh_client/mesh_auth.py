#!/usr/bin/env python
from __future__ import print_function
from mesh_client import _AuthTokenGenerator
from argparse import ArgumentParser


def main():
    parser = ArgumentParser(description="Create MESH auth token for user")
    parser.add_argument('user', help="The username")
    parser.add_argument('password', help="The password for the user")
    args = parser.parse_args()
    generator = _AuthTokenGenerator(b'BackBone', args.user, args.password)
    print(generator())


if __name__ == '__main__':
    main()
