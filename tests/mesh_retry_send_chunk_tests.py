import os.path
import re
import sys
from collections import defaultdict
from time import sleep
from typing import Dict, List, cast
from uuid import uuid4

import pytest
import requests
from pytest_httpserver import HTTPServer
from urllib3.exceptions import ResponseError
from werkzeug import Request

from mesh_client import MeshClient, SendMessageResponse_v2
from tests.helpers import bytes_response, default_ssl_opts, json_response, plain_response

alice_mailbox = "alice"
alice_password = "password"
bob_mailbox = "bob"
bob_password = "password"


@pytest.fixture(name="alice")
def alice_mesh_client(httpserver: HTTPServer):
    with MeshClient(
        httpserver.url_for(""),
        alice_mailbox,
        alice_password,
        max_chunk_size=5,
        retry_backoff_factor=0.01,
        **default_ssl_opts,  # type: ignore[arg-type]
    ) as alice:
        yield alice


@pytest.fixture(name="bob")
def bob_mesh_client(httpserver: HTTPServer):
    with MeshClient(
        httpserver.url_for(""),
        bob_mailbox,
        bob_password,
        max_chunk_size=5,
        retry_backoff_factor=0.01,
        **default_ssl_opts,  # type: ignore[arg-type]
    ) as bob:
        yield bob


@pytest.mark.skipif(sys.version_info < (3, 8), reason="requires python3.8 or higher")
def test_mesh_client_with_http_server(httpserver: HTTPServer):
    httpserver.expect_request("/messageexchange/_ping").respond_with_json({}, status=200)

    with MeshClient(httpserver.url_for(""), bob_mailbox, bob_password, max_chunk_size=5, verify=False) as client:
        client.ping()


@pytest.mark.skipif(sys.version_info < (3, 8), reason="requires python3.8 or higher")
def test_timeout(httpserver: HTTPServer):
    with MeshClient(
        httpserver.url_for(""),
        bob_mailbox,
        bob_password,
        max_chunk_size=5,
        verify=False,
        timeout=1,
        retry_backoff_factor=0.01,
    ) as client:

        def slow_handler(_request: Request):
            sleep(1.1)
            return json_response({"messages": [], "links": {}})

        httpserver.expect_request(f"{client.mailbox_path}/inbox").respond_with_handler(slow_handler)
        with pytest.raises(requests.exceptions.ConnectionError, match="ReadTimeoutError"):
            client.list_messages()


@pytest.mark.skipif(sys.version_info < (3, 8), reason="requires python3.8 or higher")
def test_no_timeout(httpserver: HTTPServer):
    with MeshClient(
        httpserver.url_for(""),
        bob_mailbox,
        bob_password,
        max_chunk_size=5,
        verify=False,
        timeout=2,
        retry_backoff_factor=0.01,
    ) as client:

        def slow_handler(_request: Request):
            sleep(1.1)
            return json_response({"messages": [], "links": {}})

        httpserver.expect_request(f"{client.mailbox_path}/inbox").respond_with_handler(slow_handler)
        client.list_messages()


def test_chunk_retries(httpserver: HTTPServer, alice: MeshClient, bob: MeshClient):
    message_id = uuid4().hex.upper()

    send_bytes = b"Hello World"

    send_re = re.compile(rf"^{alice.mailbox_path}/outbox(/{message_id}/\d+)?")

    assert send_re.match(f"{alice.mailbox_path}/outbox")
    assert send_re.match(f"{alice.mailbox_path}/outbox/{message_id}/2")

    chunk_call_counts: Dict[int, int] = defaultdict(int)
    received_chunks: List[bytes] = []

    def send_chunk_handler(request: Request):
        last_path = request.path.split("/")[-1]

        chunk_no = int(last_path) if last_path.isdigit() else 1
        chunk_call_counts[chunk_no] += 1

        if chunk_no == 1:
            received_chunks.append(request.data)
            return json_response(cast(SendMessageResponse_v2, {"message_id": message_id}), status=202)

        if chunk_no == 2 and chunk_call_counts[chunk_no] < 4:
            return plain_response("", status=502)

        received_chunks.append(request.data)

        return plain_response("")

    httpserver.expect_request(send_re, method="POST").respond_with_handler(send_chunk_handler)

    message_id_received = alice.send_message(bob_mailbox, send_bytes)

    assert message_id_received == message_id
    assert b"".join(received_chunks) == send_bytes
    assert len(received_chunks) == 3

    httpserver.expect_request(f"{bob.mailbox_path}/inbox/{message_id}", method="GET").respond_with_response(
        bytes_response(response=received_chunks[0], status=206, headers={"mex-chunk-range": "1:3"})
    )
    httpserver.expect_request(f"{bob.mailbox_path}/inbox/{message_id}/2", method="GET").respond_with_response(
        bytes_response(response=received_chunks[1], status=206, headers={"mex-chunk-range": "2:3"})
    )
    httpserver.expect_request(f"{bob.mailbox_path}/inbox/{message_id}/3", method="GET").respond_with_response(
        bytes_response(response=received_chunks[2], status=200, headers={"mex-chunk-range": "3:3"})
    )

    received = bob.retrieve_message(message_id).read()
    assert received == send_bytes

    assert chunk_call_counts[1] == 1
    assert chunk_call_counts[2] == 4
    assert chunk_call_counts[3] == 1


def test_chunk_all_retries_fail(httpserver: HTTPServer, alice: MeshClient, bob: MeshClient):
    message_id = uuid4().hex.upper()

    httpserver.expect_request(f"{alice.mailbox_path}/outbox", method="POST").respond_with_response(
        json_response(cast(SendMessageResponse_v2, {"message_id": message_id}), status=202)
    )
    send_re = re.compile(rf"^{alice.mailbox_path}/outbox/{message_id}/\d+")

    assert send_re.match(f"{alice.mailbox_path}/outbox/{message_id}/1")

    chunk_call_counts: Dict[int, int] = defaultdict(int)

    chunk_call_counts[1] += 1

    def send_chunk_handler(request: Request):
        last_path = request.path.split("/")[-1]
        chunk_no = int(last_path) if last_path.isdigit() else 1
        chunk_call_counts[chunk_no] += 1
        return plain_response("", status=502)

    httpserver.expect_request(send_re, method="POST").respond_with_handler(send_chunk_handler)

    with pytest.raises(requests.exceptions.RetryError):
        alice.send_message(bob_mailbox, b"Hello World")

    assert chunk_call_counts[1] == 1
    assert chunk_call_counts[2] == 4


def test_chunk_first_chunk_fails(httpserver: HTTPServer, alice: MeshClient, bob: MeshClient):
    message_id = uuid4().hex.upper()

    send_re = re.compile(rf"^{alice.mailbox_path}/outbox(/{message_id}/\d+)?")

    assert send_re.match(f"{alice.mailbox_path}/outbox")
    assert send_re.match(f"{alice.mailbox_path}/outbox/{message_id}/2")

    chunk_call_counts: Dict[int, int] = defaultdict(int)

    def send_chunk_handler(request: Request):
        last_path = request.path.split("/")[-1]

        chunk_no = int(last_path) if last_path.isdigit() else 1
        chunk_call_counts[chunk_no] += 1

        return plain_response("", status=502)

    httpserver.expect_request(send_re, method="POST").respond_with_handler(send_chunk_handler)

    with pytest.raises(ResponseError):
        alice.send_message(bob_mailbox, b"Hello World")

    assert chunk_call_counts[1] == 1
    assert chunk_call_counts[2] == 0


def test_chunk_retries_with_file(httpserver: HTTPServer, alice: MeshClient, bob: MeshClient, tmpdir: str):
    chunk_file = os.path.join(tmpdir, uuid4().hex)

    message_id = uuid4().hex.upper()
    send_bytes = b"test1 test2 test3"

    send_re = re.compile(rf"^{alice.mailbox_path}/outbox(/{message_id}/\d+)?")

    assert send_re.match(f"{alice.mailbox_path}/outbox")
    assert send_re.match(f"{alice.mailbox_path}/outbox/{message_id}/2")

    chunk_call_counts: Dict[int, int] = defaultdict(int)
    received_chunks: List[bytes] = []

    def send_chunk_handler(request: Request):
        last_path = request.path.split("/")[-1]

        chunk_no = int(last_path) if last_path.isdigit() else 1
        chunk_call_counts[chunk_no] += 1

        if chunk_no == 1:
            received_chunks.append(request.data)
            return json_response(cast(SendMessageResponse_v2, {"message_id": message_id}), status=202)

        if chunk_no == 2 and chunk_call_counts[chunk_no] < 4:
            return plain_response("", status=502)

        received_chunks.append(request.data)

        return plain_response("")

    httpserver.expect_request(send_re, method="POST").respond_with_handler(send_chunk_handler)

    with open(chunk_file, "wb+") as wf:
        wf.write(send_bytes)

    httpserver.expect_request(send_re, method="POST").respond_with_handler(send_chunk_handler)

    with open(chunk_file, "rb") as rf:
        alice.send_message(bob_mailbox, rf)

    assert chunk_call_counts[1] == 1
    assert chunk_call_counts[2] == 4
    assert chunk_call_counts[3] == 1

    received = b"".join(received_chunks)
    assert received == send_bytes
