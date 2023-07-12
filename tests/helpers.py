import contextlib
import os

from mesh_client import Endpoint

_PACKAGE_DIR = os.path.dirname(__file__)
MOCK_CA_CERT = os.path.join(_PACKAGE_DIR, "ca.cert.pem")
MOCK_CERT = os.path.join(_PACKAGE_DIR, "client.cert.pem")
MOCK_KEY = os.path.join(_PACKAGE_DIR, "client.key.pem")

MOCK_SSL_OPTS = {"verify": MOCK_CA_CERT, "cert": (MOCK_CERT, MOCK_KEY)}
"""
Usable default values for verify and cert, providing certificates and keys
which should work with mock_server. Note that these certs will not work with
any NHS Digital test environments - such certs must be obtained from
NHS Digital.
"""
default_ssl_opts = MOCK_SSL_OPTS

LOCAL_MOCK_ENDPOINT = Endpoint("https://localhost:8000", MOCK_CA_CERT, (MOCK_CERT, MOCK_KEY), False, False)
LOCAL_FAKE_ENDPOINT = Endpoint("https://localhost:8829", MOCK_CA_CERT, (MOCK_CERT, MOCK_KEY), False, False)
SANDBOX_ENDPOINT = Endpoint("https://localhost:8701", MOCK_CA_CERT, (MOCK_CERT, MOCK_KEY), False, False)


@contextlib.contextmanager
def temp_env_vars(**kwargs):
    """
    Temporarily set the process environment variables.
    >>> with temp_env_vars(PLUGINS_DIR=u'test/plugins'):
    ...   "PLUGINS_DIR" in os.environ
    True
    >>> "PLUGINS_DIR" in os.environ
    """
    old_environ = dict(os.environ)
    kwargs = {k: str(v) for k, v in kwargs.items()}
    os.environ.update(**kwargs)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(old_environ)
