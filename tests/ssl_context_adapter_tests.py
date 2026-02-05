from __future__ import annotations

from unittest.mock import Mock

import pytest

import mesh_client


class SSLContextStub:
    def __init__(self) -> None:
        self.load_cert_chain = Mock()
        self.load_verify_locations = Mock()
        self.minimum_version = None
        self.check_hostname = None
        self.verify_mode = None
        self.hostname_checks_common_name = None


@pytest.mark.parametrize(
    ("certs", "loads_cert_chain_called"),
    [
        (("client.crt", "client.key"), True),
        (None, False),
    ],
)
def test_create_ssl_context_loads_cert_chain(monkeypatch, certs: tuple[str, str] | None, loads_cert_chain_called: bool):

    dummy_context = SSLContextStub()
    monkeypatch.setattr(mesh_client, "create_urllib3_context", lambda: dummy_context)

    adapter = mesh_client.SSLContextAdapter(cert=certs, verify=None)
    dummy_context.load_cert_chain.reset_mock()

    context = adapter.create_ssl_context()

    assert context is dummy_context

    if loads_cert_chain_called:
        assert certs is not None
        dummy_context.load_cert_chain.assert_called_with(*certs)
    else:
        dummy_context.load_cert_chain.assert_not_called()


@pytest.mark.parametrize("verify", [True, False, "/path/to/ca.pem"])
def test_create_ssl_context_loads_verify_locations_when_verify_is_provided(monkeypatch, verify: bool | str | None):
    dummy_context = SSLContextStub()
    monkeypatch.setattr(mesh_client, "create_urllib3_context", lambda: dummy_context)

    adapter = mesh_client.SSLContextAdapter(cert=None, verify=verify)
    context = adapter.create_ssl_context()

    assert context is dummy_context

    if verify == "/path/to/ca.pem":
        dummy_context.load_verify_locations.assert_called_with(verify)
    else:
        dummy_context.load_verify_locations.assert_not_called()
