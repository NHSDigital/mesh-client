import os.path
import re
from collections import defaultdict
from typing import Dict, List, cast
from uuid import uuid4

import pytest
import requests
from pytest_httpserver import HTTPServer
from requests import HTTPError
from werkzeug import Request

from mesh_client import MeshClient, SendMessageResponse_v2
from tests.helpers import default_ssl_opts, json_response, plain_response

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
        max_retries=0,
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
        max_retries=0,
        **default_ssl_opts,  # type: ignore[arg-type]
    ) as bob:
        yield bob


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

    with pytest.raises(HTTPError):
        alice.send_message(bob_mailbox, send_bytes)

    assert chunk_call_counts[1] == 1
    assert chunk_call_counts[2] == 1
    assert chunk_call_counts[3] == 0


def test_chunk_all_retries_fail(httpserver: HTTPServer, alice: MeshClient, bob: MeshClient):
    message_id = uuid4().hex.upper()

    sent_bytes = b"Hello World"

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

        return plain_response("", status=502)

    httpserver.expect_request(send_re, method="POST").respond_with_handler(send_chunk_handler)

    with pytest.raises(requests.exceptions.HTTPError):
        alice.send_message(bob_mailbox, sent_bytes)

    assert chunk_call_counts[1] == 1
    assert chunk_call_counts[2] == 1
    assert chunk_call_counts[3] == 0
    received = b"".join(received_chunks)
    assert received == sent_bytes[:5]


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

    with pytest.raises(HTTPError), open(chunk_file, "rb") as rf:
        alice.send_message(bob_mailbox, rf)

    assert chunk_call_counts[1] == 1
    assert chunk_call_counts[2] == 1
    assert chunk_call_counts[3] == 0

    received = b"".join(received_chunks)
    assert received == send_bytes[:5]
