#!/usr/bin/env python
from __future__ import print_function
from mesh_client import AuthTokenGenerator
from mesh_client.key_helper import get_shared_key_from_environ
from argparse import ArgumentParser


def encode_bytes(key):
    return key.encode('utf-8')


def main():
    parser = ArgumentParser(description="Create MESH auth token for user")
    parser.add_argument('user', help="The username")
    parser.add_argument('password', help="The password for the user")
    parser.add_argument('--shared-key',
                        help="The shared key to use for MESH authentication",
                        default=get_shared_key_from_environ(),
                        type=encode_bytes)
    args = parser.parse_args()
    generator = AuthTokenGenerator(args.shared_key, args.user, args.password)
    print(generator.generate_token())


if __name__ == '__main__':
    main()
