import itertools
import socket
from _socket import gaierror
from ssl import SSLCertVerificationError
from urllib.parse import urlparse

import pytest
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import HTTPError, SSLError
from urllib3.exceptions import ProxyError

import mesh_client
from mesh_client import DEPRECATED_HSCN_INT_ENDPOINT, Endpoint, MeshClient
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


_ENDPOINTS = [(name, endpoint) for name, endpoint in mesh_client.ENDPOINTS if not name.startswith("LOCAL_")]

_INTERNET_ENDPOINTS = [(name, endpoint) for name, endpoint in _ENDPOINTS if not name.startswith("DEPRECATED_HSCN_")]

_HSCN_ENDPOINTS = [(name, endpoint) for name, endpoint in _ENDPOINTS if name.startswith("DEPRECATED_HSCN_")]

CONNECTION_ABORTED_ERROR = "Connection aborted."
REMOTE_END_CLOSED_CONNECTION = "Remote end closed connection without response"
SSL_CERTIFICATE_ERROR = "SSL certificate error"
LOCAL_HTTPS_PROXY_URL = "http://localhost:8019"


@pytest.mark.parametrize(("name", "endpoint"), _HSCN_ENDPOINTS)
@pytest.mark.skipif(not _host_resolves(DEPRECATED_HSCN_INT_ENDPOINT), reason="these hosts will only resolve on HSCN")
def test_hscn_endpoints(name: str, endpoint: Endpoint):
    with (
        pytest.raises((HTTPError, SSLError)) as err,
        MeshClient(endpoint, "BADUSERNAME", "BADPASSWORD", cert=(MOCK_CERT, MOCK_KEY)) as client,
    ):
        client.ping()

    if err.type == SSLError:
        assert err.value.args[0].reason.args[0].reason == "CERTIFICATE_VERIFY_FAILED"
    else:
        assert err.value.response is not None
        assert err.value.response.status_code == 400


@pytest.mark.parametrize(("name", "endpoint"), _HSCN_ENDPOINTS)
@pytest.mark.skipif(not _host_resolves(DEPRECATED_HSCN_INT_ENDPOINT), reason="these hosts will only resolve on HSCN")
def test_hscn_endpoints_verify_false(name: str, endpoint: Endpoint):
    with (
        pytest.raises((HTTPError, SSLError)) as err,
        MeshClient(endpoint.url, "BADUSERNAME", "BADPASSWORD", cert=(MOCK_CERT, MOCK_KEY), verify=False) as client,
    ):
        client.ping()

    if err.type == SSLError:
        assert err.value.args[0].reason.args[0].reason == "CERTIFICATE_VERIFY_FAILED"
    else:
        assert err.value.response is not None
        assert err.value.response.status_code == 400


@pytest.mark.parametrize(("name", "endpoint"), _HSCN_ENDPOINTS)
@pytest.mark.skipif(not _host_resolves(DEPRECATED_HSCN_INT_ENDPOINT), reason="these hosts will only resolve on HSCN")
def test_hscn_endpoints_defaults_from_hostname(name: str, endpoint: Endpoint):
    with (
        pytest.raises((HTTPError, SSLError)) as err,
        MeshClient(endpoint.url, "BADUSERNAME", "BADPASSWORD", cert=(MOCK_CERT, MOCK_KEY)) as client,
    ):
        client.ping()

    if err.type == SSLError:
        assert err.value.args[0].reason.args[0].reason == "CERTIFICATE_VERIFY_FAILED"
    else:
        assert err.value.response is not None
        assert err.value.response.status_code == 400
        assert err.value.args[0] == f"400 Client Error: Bad Request for url: {endpoint.url}/messageexchange/_ping"
        assert SSL_CERTIFICATE_ERROR in err.value.response.text


@pytest.mark.parametrize(("name", "endpoint"), _HSCN_ENDPOINTS)
@pytest.mark.skipif(not _host_resolves(DEPRECATED_HSCN_INT_ENDPOINT), reason="these hosts will only resolve on HSCN")
def test_dep_hscn_endpoint_common_name_check_false(name: str, endpoint: Endpoint):
    with (
        pytest.raises((SSLError, HTTPError)) as err,
        MeshClient(
            endpoint, "BADUSERNAME", "BADPASSWORD", cert=(MOCK_CERT, MOCK_KEY), hostname_checks_common_name=False
        ) as client,
    ):
        client.ping()

    if err.type == SSLError:
        assert err.value.args[0].reason.args[0].reason == "CERTIFICATE_VERIFY_FAILED"
    else:
        assert err.value.response is not None
        assert err.value.args[0] == f"400 Client Error: Bad Request for url: {endpoint.url}/messageexchange/_ping"
        assert SSL_CERTIFICATE_ERROR in err.value.response.text
        assert err.value.response.status_code == 400


@pytest.mark.parametrize(("name", "endpoint"), _INTERNET_ENDPOINTS)
def test_internet_endpoints(name: str, endpoint: Endpoint):
    with (
        pytest.raises((RequestsConnectionError, SSLError)) as err,
        MeshClient(endpoint, "BADUSERNAME", "BADPASSWORD", cert=(MOCK_CERT, MOCK_KEY)) as client,
    ):
        client.ping()

    if err.type == SSLError:
        assert isinstance(err.value.args[0].reason.args[0], SSLCertVerificationError)
    else:
        assert isinstance(err.value.args[0].reason.args[1], ConnectionResetError)


@pytest.mark.parametrize(("name", "endpoint"), _INTERNET_ENDPOINTS)
def test_internet_endpoints_common_name_check_false(name: str, endpoint: Endpoint):
    with (
        pytest.raises((RequestsConnectionError, SSLError)) as err,
        MeshClient(
            endpoint, "BADUSERNAME", "BADPASSWORD", cert=(MOCK_CERT, MOCK_KEY), hostname_checks_common_name=False
        ) as client,
    ):
        client.ping()

    if err.type == SSLError:
        assert isinstance(err.value.args[0].reason.args[0], SSLCertVerificationError)
    else:
        assert isinstance(err.value.args[0].reason.args[1], ConnectionResetError)


@pytest.mark.parametrize(("name", "endpoint"), _INTERNET_ENDPOINTS)
def test_internet_endpoints_verify_false(name: str, endpoint: Endpoint):
    with (
        pytest.raises((RequestsConnectionError, SSLError)) as err,
        MeshClient(endpoint.url, "BADUSERNAME", "BADPASSWORD", cert=(MOCK_CERT, MOCK_KEY), verify=False) as client,
    ):
        client.ping()

    if err.type == SSLError:
        assert isinstance(err.value.args[0].reason.args[0], SSLCertVerificationError)
    else:
        assert isinstance(err.value.args[0].reason.args[1], ConnectionResetError)


@pytest.mark.parametrize(("name", "endpoint"), _INTERNET_ENDPOINTS)
def test_internet_endpoints_defaults_from_hostname(name: str, endpoint: Endpoint):
    with (
        pytest.raises((RequestsConnectionError, SSLError)) as err,
        MeshClient(endpoint.url, "BADUSERNAME", "BADPASSWORD", cert=(MOCK_CERT, MOCK_KEY), verify=None) as client,
    ):
        client.ping()

    if err.type == SSLError:
        assert isinstance(err.value.args[0].reason.args[0], SSLCertVerificationError)
    else:
        assert isinstance(err.value.args[0].reason.args[1], ConnectionResetError)


@pytest.mark.parametrize(("name", "endpoint"), _INTERNET_ENDPOINTS)
def test_internet_endpoints_with_port_defaults_from_hostname(name: str, endpoint: Endpoint):
    with (
        pytest.raises((RequestsConnectionError, SSLError)) as err,
        MeshClient(
            f"{endpoint.url}:443", "BADUSERNAME", "BADPASSWORD", cert=(MOCK_CERT, MOCK_KEY), verify=None
        ) as client,
    ):
        client.ping()

    if err.type == SSLError:
        assert isinstance(err.value.args[0].reason.args[0], SSLCertVerificationError)
    else:
        assert isinstance(err.value.args[0].reason.args[1], ConnectionResetError)


@pytest.mark.parametrize(
    ("name", "endpoint", "check_hostname"),
    [(ep[0], ep[1], check_hostname) for check_hostname, ep in itertools.product([True, False, None], _HSCN_ENDPOINTS)],
)
@pytest.mark.skipif(not _host_resolves(DEPRECATED_HSCN_INT_ENDPOINT), reason="these hosts will only resolve on HSCN")
def test_hscn_endpoints_check_hostname(name: str, endpoint: Endpoint, check_hostname: bool):
    with (
        pytest.raises((HTTPError, SSLError)) as err,
        MeshClient(
            endpoint.url,
            "BADUSERNAME",
            "BADPASSWORD",
            cert=(MOCK_CERT, MOCK_KEY),
            verify=endpoint.verify,
            check_hostname=check_hostname,
        ) as client,
    ):
        client.ping()

    if err.type == SSLError:
        assert isinstance(err.value.args[0].reason.args[0], SSLCertVerificationError)
    else:
        assert err.value.response is not None
        assert err.value.args[0] == f"400 Client Error: Bad Request for url: {endpoint.url}/messageexchange/_ping"
        assert SSL_CERTIFICATE_ERROR in err.value.response.text
        assert err.value.response.status_code == 400


@pytest.mark.parametrize(
    ("name", "endpoint", "check_hostname"),
    [(ep[0], ep[1], check_hostname) for check_hostname, ep in itertools.product([True, False], _INTERNET_ENDPOINTS)],
)
def test_internet_endpoints_check_hostname(name: str, endpoint: Endpoint, check_hostname: bool):
    with (
        pytest.raises((RequestsConnectionError, SSLError)) as err,
        MeshClient(
            endpoint.url,
            "BADUSERNAME",
            "BADPASSWORD",
            cert=(MOCK_CERT, MOCK_KEY),
            verify=endpoint.verify,
            check_hostname=check_hostname,
        ) as client,
    ):
        client.ping()

    if err.type == SSLError:
        assert isinstance(err.value.args[0].reason.args[0], SSLCertVerificationError)
    else:
        assert err.value.response is None
        assert isinstance(err.value.args[0].reason.args[1], ConnectionResetError)


@pytest.mark.parametrize(("name", "endpoint"), _HSCN_ENDPOINTS)
@pytest.mark.skipif(not _host_resolves(DEPRECATED_HSCN_INT_ENDPOINT), reason="these hosts will only resolve on HSCN")
def test_hscn_endpoints_via_an_explicit_proxy(name: str, endpoint: Endpoint):
    with (
        pytest.raises((HTTPError, SSLError)) as err,
        MeshClient(
            endpoint,
            "BADUSERNAME",
            "BADPASSWORD",
            cert=(MOCK_CERT, MOCK_KEY),
            proxies={"https": LOCAL_HTTPS_PROXY_URL},
            timeout=10,
        ) as client,
    ):
        client.ping()

    if err.type == SSLError:
        assert isinstance(err.value.args[0].reason.args[0], SSLCertVerificationError)
    else:
        assert err.value.response is not None
        assert err.value.args[0] == f"400 Client Error: Bad Request for url: {endpoint.url}/messageexchange/_ping"
        assert SSL_CERTIFICATE_ERROR in err.value.response.text
        assert err.value.response.status_code == 400


@pytest.mark.parametrize(("name", "endpoint"), _HSCN_ENDPOINTS)
@pytest.mark.skipif(not _host_resolves(DEPRECATED_HSCN_INT_ENDPOINT), reason="these hosts will only resolve on HSCN")
def test_hscn_endpoints_via_an_ambient_proxy(name: str, endpoint: Endpoint):
    with (
        temp_env_vars(HTTPS_PROXY=LOCAL_HTTPS_PROXY_URL),
        pytest.raises((HTTPError, SSLError)) as err,
        MeshClient(endpoint, "BADUSERNAME", "BADPASSWORD", cert=(MOCK_CERT, MOCK_KEY)) as client,
    ):
        client.ping()

    if err.type == SSLError:
        assert isinstance(err.value.args[0].reason.args[0], SSLCertVerificationError)
    else:
        assert err.value.response is not None
        assert err.value.args[0] == f"400 Client Error: Bad Request for url: {endpoint.url}/messageexchange/_ping"
        assert SSL_CERTIFICATE_ERROR in err.value.response.text
        assert err.value.response.status_code == 400


@pytest.mark.parametrize(("name", "endpoint"), _INTERNET_ENDPOINTS)
def test_internet_endpoints_via_explicit_proxy(name: str, endpoint: Endpoint):
    with (
        pytest.raises((RequestsConnectionError, SSLError)) as err,
        MeshClient(
            endpoint,
            "BADUSERNAME",
            "BADPASSWORD",
            cert=(MOCK_CERT, MOCK_KEY),
            proxies={"https": LOCAL_HTTPS_PROXY_URL},
        ) as client,
    ):
        client.handshake()

    if err.type == SSLError:
        assert isinstance(err.value.args[0].reason.args[0], SSLCertVerificationError)
    else:
        assert isinstance(err.value.args[0].reason, ProxyError)
        assert str(err.value.args[0].reason.args[1]) == REMOTE_END_CLOSED_CONNECTION


@pytest.mark.parametrize(("name", "endpoint"), _INTERNET_ENDPOINTS)
def test_internet_endpoints_via_ambient_proxy(name: str, endpoint: Endpoint):
    with (
        temp_env_vars(HTTPS_PROXY=LOCAL_HTTPS_PROXY_URL),
        pytest.raises((RequestsConnectionError, SSLError)) as err,
        MeshClient(endpoint, "BADUSERNAME", "BADPASSWORD", cert=(MOCK_CERT, MOCK_KEY)) as client,
    ):
        client.handshake()

    if err.type == SSLError:
        assert isinstance(err.value.args[0].reason.args[0], SSLCertVerificationError)
    else:
        assert isinstance(err.value.args[0].reason, ProxyError)
        assert str(err.value.args[0].reason.args[1]) == REMOTE_END_CLOSED_CONNECTION
