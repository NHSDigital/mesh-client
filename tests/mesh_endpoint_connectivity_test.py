import socket
from urllib.parse import urlparse

import pytest
from _socket import gaierror
from requests.exceptions import HTTPError, SSLError

import mesh_client
from mesh_client import MOCK_CERT, MOCK_KEY, NHS_INT_ENDPOINT, Endpoint, MeshClient


def _host_resolves(endpoint: Endpoint):
    parsed = urlparse(endpoint.url)
    try:
        socket.gethostbyname(str(parsed.hostname))
    except gaierror as err:
        if err.args[1] == "Name or service not known":
            return False
        raise
    return True


_ENDPOINTS = [
    (name, endpoint)
    for name, endpoint in mesh_client.__dict__.items()
    if name.endswith("_ENDPOINT") and not name.startswith("LOCAL_") and "_OPENTEST_" not in name
]

_INTERNET_ENDPOINTS = [(name, endpoint) for name, endpoint in _ENDPOINTS if "_INTERNET_GATEWAY" in name]

_HSCN_ENDPOINTS = [(name, endpoint) for name, endpoint in _ENDPOINTS if "_INTERNET_GATEWAY" not in name]


@pytest.mark.parametrize("name, endpoint", _HSCN_ENDPOINTS)
@pytest.mark.skipif(not _host_resolves(NHS_INT_ENDPOINT), reason="these hosts will only resolve on HSCN")
def test_hscn_endpoints(name: str, endpoint: Endpoint):
    with pytest.raises(HTTPError) as err:
        client = MeshClient(endpoint, "BADUSERNAME", "BADPASSWORD")
        client.ping()

    assert err.value.response.status_code == 400


@pytest.mark.parametrize("name, endpoint", _INTERNET_ENDPOINTS)
def test_live_internet_endpoint(name: str, endpoint: Endpoint):
    with pytest.raises(SSLError) as err:
        client = MeshClient(endpoint, "BADUSERNAME", "BADPASSWORD", cert=(MOCK_CERT, MOCK_KEY))
        client.ping()

    # the internet endpoints behave differently they will not return a 400 bad request
    # in this case, TLSV1_ALERT_UNKNOWN_CA actually means "I don't accept this client certificate"
    assert err.value.args[0].reason.args[0].reason == "TLSV1_ALERT_UNKNOWN_CA"
