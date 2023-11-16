import json
import os.path
import re
import sys
from collections import defaultdict
from time import sleep
from typing import Dict, Mapping, Optional, cast
from uuid import uuid4

import pytest
import requests
from pytest_httpserver import HTTPServer
from werkzeug import Request, Response

from mesh_client import MeshClient, SendMessageResponse_v2
from tests.helpers import default_ssl_opts

alice_mailbox = "alice"
alice_password = "password"
bob_mailbox = "bob"
bob_password = "password"


def json_response(
    response: dict,
    status: int = 200,
    content_type: str = "application/vnd.mesh.v2+json",
    headers: Optional[Mapping[str, str]] = None,
) -> Response:
    return Response(response=json.dumps(response), status=status, content_type=content_type, headers=headers)


def bytes_response(
    response: bytes,
    status: int = 200,
    content_type: str = "application/octet-stream",
    headers: Optional[Mapping[str, str]] = None,
) -> Response:
    return Response(response=response, status=status, content_type=content_type, headers=headers)


def plain_response(
    response: str, status: int = 200, content_type: str = "text/plain", headers: Optional[Mapping[str, str]] = None
) -> Response:
    return Response(response=response, status=status, content_type=content_type, headers=headers)


@pytest.mark.skipif(sys.version_info < (3, 8), reason="requires python3.8 or higher")
def test_mesh_client_with_http_server(httpserver: HTTPServer):
    httpserver.expect_request("/messageexchange/_ping").respond_with_json({}, status=200)

    with MeshClient(
        httpserver.url_for("").rstrip("/"), bob_mailbox, bob_password, max_chunk_size=5, verify=False
    ) as client:
        client.ping()


@pytest.mark.skipif(sys.version_info < (3, 8), reason="requires python3.8 or higher")
def test_timeout(httpserver: HTTPServer):
    with MeshClient(
        httpserver.url_for("").rstrip("/"), bob_mailbox, bob_password, max_chunk_size=5, verify=False, timeout=1
    ) as client:

        def slow_handler(_request: Request):
            sleep(1.1)
            return json_response({"messages": [], "links": {}})

        httpserver.expect_request(f"{client.mailbox_path}/inbox").respond_with_handler(slow_handler)
        with pytest.raises(requests.exceptions.Timeout):
            client.list_messages()


@pytest.fixture(name="alice")
def alice_mesh_client(httpserver: HTTPServer):
    with MeshClient(
        httpserver.url_for("").rstrip("/"),
        alice_mailbox,
        alice_password,
        max_chunk_size=5,
        max_chunk_retries=3,
        **default_ssl_opts,  # type: ignore[arg-type]
    ) as alice:
        yield alice


@pytest.fixture(name="bob")
def bob_mesh_client(httpserver: HTTPServer):
    with MeshClient(
        httpserver.url_for("").rstrip("/"),
        bob_mailbox,
        bob_password,
        max_chunk_size=5,
        max_chunk_retries=3,
        **default_ssl_opts,  # type: ignore[arg-type]
    ) as bob:
        yield bob


def _count_chunk_retry_call_counts(mocked_post):
    counts: Dict[int, int] = {}
    for call in mocked_post.call_args_list:
        chunk = int(call.kwargs["headers"]["Mex-Chunk-Range"].split(":")[0])
        if chunk not in counts:
            counts[chunk] = 0
        else:
            counts[chunk] += 1
    return counts


def test_chunk_retries(httpserver: HTTPServer, alice: MeshClient, bob: MeshClient):
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
        if chunk_no == 2 and chunk_call_counts[chunk_no] < 4:
            return plain_response("", status=502)

        return plain_response("")

    httpserver.expect_request(send_re, method="POST").respond_with_handler(send_chunk_handler)

    httpserver.expect_request(f"{bob.mailbox_path}/inbox/{message_id}", method="GET").respond_with_response(
        bytes_response(response=b"Hello", status=206, headers={"mex-chunk-range": "1:3"})
    )
    httpserver.expect_request(f"{bob.mailbox_path}/inbox/{message_id}/2", method="GET").respond_with_response(
        bytes_response(response=b" Worl", status=206, headers={"mex-chunk-range": "2:3"})
    )
    httpserver.expect_request(f"{bob.mailbox_path}/inbox/{message_id}/3", method="GET").respond_with_response(
        bytes_response(response=b"d", status=200, headers={"mex-chunk-range": "3:3"})
    )

    message_id = alice.send_message(bob_mailbox, b"Hello World")

    received = bob.retrieve_message(message_id).read()
    assert received == b"Hello World"

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

    with pytest.raises(requests.exceptions.HTTPError):
        alice.send_message(bob_mailbox, b"Hello World")

    assert chunk_call_counts[1] == 1
    assert chunk_call_counts[2] == 4


def test_chunk_retries_with_file(httpserver: HTTPServer, alice: MeshClient, bob: MeshClient, tmpdir: str):
    chunk_file = os.path.join(tmpdir, uuid4().hex)

    with open(chunk_file, "wb+") as wf:
        wf.write(b"test1 test2 test3")

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
        if chunk_no == 2 and chunk_call_counts[chunk_no] < 4:
            return plain_response("", status=502)

        return plain_response("")

    httpserver.expect_request(send_re, method="POST").respond_with_handler(send_chunk_handler)

    with open(chunk_file, "rb") as rf:
        alice.send_message(bob_mailbox, rf)

    assert chunk_call_counts[1] == 1
    assert chunk_call_counts[2] == 4
    assert chunk_call_counts[3] == 1
