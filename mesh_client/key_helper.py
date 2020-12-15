import os


def get_shared_key_from_environ():
    key = os.environ.get(
        'MESH_CLIENT_SHARED_KEY',
        '\x42\x61\x63\x6b\x42\x6f\x6e\x65'
    )
    if not isinstance(key, bytes):
        # Handle Python 3's non-Posix handling of binary environment variables
        key = key.encode('utf-8', 'surrogateescape')
    return key
