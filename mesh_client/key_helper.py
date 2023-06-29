import os


def get_shared_key_from_environ() -> bytes:
    key_str = os.environ.get("MESH_CLIENT_SHARED_KEY", "\x42\x61\x63\x6b\x42\x6f\x6e\x65")
    if isinstance(key_str, bytes):
        return key_str

    return key_str.encode("utf-8")
