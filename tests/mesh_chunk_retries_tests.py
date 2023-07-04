import os.path
from collections import namedtuple
from typing import Dict
from uuid import uuid4

import mock
import pytest
import requests

from mesh_client import MeshClient
from tests.helpers import default_ssl_opts
from tests.mock_server import MockMeshChunkRetryApplication

alice_mailbox = "alice"
alice_password = "password"
bob_mailbox = "bob"
bob_password = "password"


@pytest.fixture(scope="function", name="mock_app")
def _mock_mesh_app():
    with MockMeshChunkRetryApplication() as mock_app:
        yield mock_app


@pytest.fixture(scope="function", name="alice")
def _alice_mesh_client(mock_app: MockMeshChunkRetryApplication):
    with MeshClient(
        mock_app.uri,
        alice_mailbox,
        alice_password,
        max_chunk_size=5,
        max_chunk_retries=3,
        **default_ssl_opts,  # type: ignore[arg-type]
    ) as alice:
        yield alice


@pytest.fixture(scope="function", name="bob")
def _bob_mesh_client(mock_app: MockMeshChunkRetryApplication):
    with MeshClient(
        mock_app.uri,
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
        if chunk not in counts.keys():
            counts[chunk] = 0
        else:
            counts[chunk] += 1
    return counts


def test_chunk_retries(mock_app: MockMeshChunkRetryApplication, alice: MeshClient, bob: MeshClient):
    mock_post = mock.Mock(wraps=alice._session.post)
    alice._session.post = mock_post  # type: ignore[method-assign]

    chunk_options = namedtuple("chunk_options", "chunk_num num_retry_attempts")
    options = [chunk_options(2, 2)]
    mock_app.set_chunk_retry_options(options)

    message_id = alice.send_message(bob_mailbox, b"Hello World")

    received = bob.retrieve_message(message_id).read()
    assert received == b"Hello World"

    chunk_retry_call_counts = _count_chunk_retry_call_counts(mock_post)
    assert chunk_retry_call_counts[1] == 0
    assert chunk_retry_call_counts[2] == 3
    assert chunk_retry_call_counts[3] == 0


def test_chunk_all_retries_fail(mock_app: MockMeshChunkRetryApplication, alice: MeshClient, bob: MeshClient):
    mock_post = mock.Mock(wraps=alice._session.post)
    alice._session.post = mock_post  # type: ignore[method-assign]

    chunk_options = namedtuple("chunk_options", "chunk_num num_retry_attempts")
    options = [chunk_options(2, 3)]
    mock_app.set_chunk_retry_options(options)

    with pytest.raises(requests.exceptions.HTTPError):
        alice.send_message(bob_mailbox, b"Hello World")

    chunk_retry_call_counts = _count_chunk_retry_call_counts(mock_post)
    assert chunk_retry_call_counts[1] == 0
    assert chunk_retry_call_counts[2] == 3


def test_chunk_retries_with_file(
    mock_app: MockMeshChunkRetryApplication, alice: MeshClient, bob: MeshClient, tmpdir: str
):
    chunk_file = os.path.join(tmpdir, uuid4().hex)

    with open(chunk_file, "wb+") as f:
        f.write(b"test1 test2 test3")

    mock_post = mock.Mock(wraps=alice._session.post)
    alice._session.post = mock_post  # type: ignore[method-assign]

    chunk_options = namedtuple("chunk_options", "chunk_num num_retry_attempts")
    options = [chunk_options(2, 2)]
    mock_app.set_chunk_retry_options(options)

    message_id = alice.send_message(bob_mailbox, open(chunk_file, "rb"))

    received = bob.retrieve_message(message_id).read()
    assert received == b"test1 test2 test3"

    chunk_retry_call_counts = _count_chunk_retry_call_counts(mock_post)
    assert chunk_retry_call_counts[1] == 0
    assert chunk_retry_call_counts[2] == 3
    assert chunk_retry_call_counts[3] == 0
