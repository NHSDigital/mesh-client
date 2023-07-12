import itertools
import socket
from urllib.parse import urlparse

import pytest
from _socket import gaierror
from requests.exceptions import HTTPError, SSLError

import mesh_client
from mesh_client import NHS_INT_ENDPOINT, Endpoint, MeshClient
from tests.helpers import MOCK_CERT, MOCK_KEY, temp_env_vars


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
    for name, endpoint in mesh_client.ENDPOINTS
    if not name.startswith("LOCAL_") and "_OPENTEST_" not in name
]

_INTERNET_ENDPOINTS = [(name, endpoint) for name, endpoint in _ENDPOINTS if "_INTERNET_GATEWAY" in name]

_HSCN_ENDPOINTS = [(name, endpoint) for name, endpoint in _ENDPOINTS if "_INTERNET_GATEWAY" not in name]


@pytest.mark.parametrize("name, endpoint", _HSCN_ENDPOINTS)
@pytest.mark.skipif(not _host_resolves(NHS_INT_ENDPOINT), reason="these hosts will only resolve on HSCN")
def test_hscn_endpoints(name: str, endpoint: Endpoint):
    with pytest.raises(HTTPError) as err:
        with MeshClient(endpoint, "BADUSERNAME", "BADPASSWORD", cert=(MOCK_CERT, MOCK_KEY)) as client:
            client.ping()

    assert err.value.response.status_code == 400


@pytest.mark.parametrize("name, endpoint", _HSCN_ENDPOINTS)
@pytest.mark.skipif(not _host_resolves(NHS_INT_ENDPOINT), reason="these hosts will only resolve on HSCN")
def test_hscn_endpoints_verify_false(name: str, endpoint: Endpoint):
    with pytest.raises(HTTPError) as err:
        with MeshClient(endpoint.url, "BADUSERNAME", "BADPASSWORD", cert=(MOCK_CERT, MOCK_KEY), verify=False) as client:
            client.ping()

    assert err.value.response.status_code == 400


@pytest.mark.parametrize("name, endpoint", _HSCN_ENDPOINTS)
@pytest.mark.skipif(not _host_resolves(NHS_INT_ENDPOINT), reason="these hosts will only resolve on HSCN")
def test_hscn_endpoints_defaults_from_hostname(name: str, endpoint: Endpoint):
    with pytest.raises(HTTPError) as err:
        with MeshClient(endpoint.url, "BADUSERNAME", "BADPASSWORD", cert=(MOCK_CERT, MOCK_KEY)) as client:
            client.ping()

    assert err.value.response.status_code == 400


@pytest.mark.parametrize("name, endpoint", _HSCN_ENDPOINTS)
@pytest.mark.skipif(not _host_resolves(NHS_INT_ENDPOINT), reason="these hosts will only resolve on HSCN")
def test_hscn_endpoints_common_name_check_false(name: str, endpoint: Endpoint):
    with pytest.raises(SSLError) as err:
        with MeshClient(
            endpoint, "BADUSERNAME", "BADPASSWORD", cert=(MOCK_CERT, MOCK_KEY), hostname_checks_common_name=False
        ) as client:
            client.ping()

    assert err.value.args[0].reason.args[0].reason == "CERTIFICATE_VERIFY_FAILED"


@pytest.mark.parametrize("name, endpoint", _INTERNET_ENDPOINTS)
def test_internet_endpoints(name: str, endpoint: Endpoint):
    with pytest.raises(SSLError) as err:
        with MeshClient(endpoint, "BADUSERNAME", "BADPASSWORD", cert=(MOCK_CERT, MOCK_KEY)) as client:
            client.ping()

    # the internet endpoints behave differently they will not return a 400 bad request
    # in this case, TLSV1_ALERT_UNKNOWN_CA actually means "I don't accept this client certificate"
    assert err.value.args[0].reason.args[0].reason == "TLSV1_ALERT_UNKNOWN_CA"


@pytest.mark.parametrize("name, endpoint", _INTERNET_ENDPOINTS)
def test_internet_endpoints_common_name_check_false(name: str, endpoint: Endpoint):
    with pytest.raises(SSLError) as err:
        with MeshClient(
            endpoint, "BADUSERNAME", "BADPASSWORD", cert=(MOCK_CERT, MOCK_KEY), hostname_checks_common_name=False
        ) as client:
            client.ping()

    # the internet endpoints behave differently they will not return a 400 bad request
    # in this case, TLSV1_ALERT_UNKNOWN_CA actually means "I don't accept this client certificate"
    if endpoint.hostname_checks_common_name:
        assert err.value.args[0].reason.args[0].reason == "CERTIFICATE_VERIFY_FAILED"
    else:
        assert err.value.args[0].reason.args[0].reason == "TLSV1_ALERT_UNKNOWN_CA"


@pytest.mark.parametrize("name, endpoint", _INTERNET_ENDPOINTS)
def test_internet_endpoints_verify_false(name: str, endpoint: Endpoint):
    with pytest.raises(SSLError) as err:
        with MeshClient(endpoint.url, "BADUSERNAME", "BADPASSWORD", cert=(MOCK_CERT, MOCK_KEY), verify=False) as client:
            client.ping()

    # the internet endpoints behave differently they will not return a 400 bad request
    # in this case, TLSV1_ALERT_UNKNOWN_CA actually means "I don't accept this client certificate"
    assert err.value.args[0].reason.args[0].reason == "TLSV1_ALERT_UNKNOWN_CA"


@pytest.mark.parametrize("name, endpoint", _INTERNET_ENDPOINTS)
def test_internet_endpoints_defaults_from_hostname(name: str, endpoint: Endpoint):
    with pytest.raises(SSLError) as err:
        with MeshClient(endpoint.url, "BADUSERNAME", "BADPASSWORD", cert=(MOCK_CERT, MOCK_KEY), verify=None) as client:
            client.ping()

    # the internet endpoints behave differently they will not return a 400 bad request
    # in this case, TLSV1_ALERT_UNKNOWN_CA actually means "I don't accept this client certificate"
    assert err.value.args[0].reason.args[0].reason == "TLSV1_ALERT_UNKNOWN_CA"


@pytest.mark.parametrize("name, endpoint", _INTERNET_ENDPOINTS)
def test_internet_endpoints_with_port_defaults_from_hostname(name: str, endpoint: Endpoint):
    with pytest.raises(SSLError) as err:
        with MeshClient(
            f"{endpoint.url}:443", "BADUSERNAME", "BADPASSWORD", cert=(MOCK_CERT, MOCK_KEY), verify=None
        ) as client:
            client.ping()

    # the internet endpoints behave differently they will not return a 400 bad request
    # in this case, TLSV1_ALERT_UNKNOWN_CA actually means "I don't accept this client certificate"
    assert err.value.args[0].reason.args[0].reason == "TLSV1_ALERT_UNKNOWN_CA"


@pytest.mark.parametrize(
    "name, endpoint, check_hostname",
    [(ep[0], ep[1], check_hostname) for check_hostname, ep in itertools.product([True, False, None], _HSCN_ENDPOINTS)],
)
@pytest.mark.skipif(not _host_resolves(NHS_INT_ENDPOINT), reason="these hosts will only resolve on HSCN")
def test_hscn_endpoints_check_hostname(name: str, endpoint: Endpoint, check_hostname: bool):
    with pytest.raises(HTTPError) as err:
        with MeshClient(
            endpoint.url,
            "BADUSERNAME",
            "BADPASSWORD",
            cert=(MOCK_CERT, MOCK_KEY),
            verify=endpoint.verify,
            check_hostname=check_hostname,
        ) as client:
            client.ping()

    assert err.value.response.status_code == 400


@pytest.mark.parametrize(
    "name, endpoint, check_hostname",
    [(ep[0], ep[1], check_hostname) for check_hostname, ep in itertools.product([True, False], _INTERNET_ENDPOINTS)],
)
def test_internet_endpoints_check_hostname(name: str, endpoint: Endpoint, check_hostname: bool):
    with pytest.raises(SSLError) as err:
        with MeshClient(
            endpoint.url,
            "BADUSERNAME",
            "BADPASSWORD",
            cert=(MOCK_CERT, MOCK_KEY),
            verify=endpoint.verify,
            check_hostname=check_hostname,
        ) as client:
            client.ping()

    # the internet endpoints behave differently they will not return a 400 bad request
    # in this case, TLSV1_ALERT_UNKNOWN_CA actually means "I don't accept this client certificate"
    assert err.value.args[0].reason.args[0].reason == "TLSV1_ALERT_UNKNOWN_CA"


@pytest.mark.parametrize("name, endpoint", _HSCN_ENDPOINTS)
@pytest.mark.skipif(not _host_resolves(NHS_INT_ENDPOINT), reason="these hosts will only resolve on HSCN")
def test_hscn_endpoints_via_an_explicit_proxy(name: str, endpoint: Endpoint):
    with pytest.raises(HTTPError) as err:
        with MeshClient(
            endpoint,
            "BADUSERNAME",
            "BADPASSWORD",
            cert=(MOCK_CERT, MOCK_KEY),
            proxies={"https": "http://localhost:8019"},
        ) as client:
            client.ping()

    assert err.value.response.status_code == 400


@pytest.mark.parametrize("name, endpoint", _HSCN_ENDPOINTS)
@pytest.mark.skipif(not _host_resolves(NHS_INT_ENDPOINT), reason="these hosts will only resolve on HSCN")
def test_hscn_endpoints_via_an_ambient_proxy(name: str, endpoint: Endpoint):
    with temp_env_vars(HTTPS_PROXY="http://localhost:8019"):
        with pytest.raises(HTTPError) as err:
            with MeshClient(endpoint, "BADUSERNAME", "BADPASSWORD", cert=(MOCK_CERT, MOCK_KEY)) as client:
                client.ping()

    assert err.value.response.status_code == 400


@pytest.mark.parametrize("name, endpoint", _INTERNET_ENDPOINTS)
def test_internet_endpoints_via_explicit_proxy(name: str, endpoint: Endpoint):
    with pytest.raises(SSLError) as err:
        with MeshClient(
            endpoint,
            "BADUSERNAME",
            "BADPASSWORD",
            cert=(MOCK_CERT, MOCK_KEY),
            proxies={"https": "http://localhost:8019"},
        ) as client:
            client.handshake()

    # the internet endpoints behave differently they will not return a 400 bad request
    # in this case, TLSV1_ALERT_UNKNOWN_CA actually means "I don't accept this client certificate"
    assert err.value.args[0].reason.args[0].reason == "TLSV1_ALERT_UNKNOWN_CA"


@pytest.mark.parametrize("name, endpoint", _INTERNET_ENDPOINTS)
def test_internet_endpoints_via_ambient_proxy(name: str, endpoint: Endpoint):
    with temp_env_vars(HTTPS_PROXY="http://localhost:8019"):
        with pytest.raises(SSLError) as err:
            with MeshClient(endpoint, "BADUSERNAME", "BADPASSWORD", cert=(MOCK_CERT, MOCK_KEY)) as client:
                client.handshake()

    # the internet endpoints behave differently they will not return a 400 bad request
    # in this case, TLSV1_ALERT_UNKNOWN_CA actually means "I don't accept this client certificate"
    assert err.value.args[0].reason.args[0].reason == "TLSV1_ALERT_UNKNOWN_CA"
