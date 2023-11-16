import io
import os.path
from typing import List, cast
from uuid import uuid4

import pytest
import requests
from requests import HTTPError

from mesh_client import CombineStreams, MeshClient, MeshError
from tests.helpers import SANDBOX_ENDPOINT, temp_env_vars

alice_mailbox = "ALICE"
alice_password = "password"
bob_mailbox = "BOB"
bob_password = "password"


class TestError(Exception):
    pass


def sandbox_uri(path: str) -> str:
    return os.path.join(SANDBOX_ENDPOINT.url, path)


@pytest.fixture(scope="module", autouse=True)
def _default_vars():
    with temp_env_vars(MESH_CLIENT_SHARED_KEY="TestKey"):
        yield


@pytest.fixture(autouse=True)
def _resets():
    res = requests.delete(sandbox_uri("admin/reset"), verify=SANDBOX_ENDPOINT.verify)
    res.raise_for_status()


@pytest.fixture(name="alice")
def alice_client():
    with MeshClient(SANDBOX_ENDPOINT, alice_mailbox, alice_password, max_chunk_size=5) as client:
        yield client


@pytest.fixture(name="bob")
def bob_client():
    with MeshClient(SANDBOX_ENDPOINT, bob_mailbox, bob_password, max_chunk_size=5) as client:
        yield client


def test_get_version():
    from mesh_client import __version__

    assert __version__ != "unknown"
    assert __version__ != "0.0.0"


def test_alice_ping(alice: MeshClient):
    alice.ping()


def test_bob_ping(bob: MeshClient):
    bob.ping()


def test_handshake(alice: MeshClient, bob: MeshClient):
    hand_shook = alice.handshake()
    assert hand_shook == b"hello"


def test_list_messages_with_a_max_results(alice: MeshClient, bob: MeshClient):
    message_ids = []
    total = 30
    page_size = 10
    for _ in range(total):
        message_id = alice.send_message(bob_mailbox, b"Hello Bob 1", workflow_id=uuid4().hex)
        message_ids.append(message_id)
    assert bob.list_messages(max_results=page_size) == message_ids[:page_size]


def test_list_messages_with_a_max_results_low(bob: MeshClient):
    with pytest.raises(ValueError, match=">= 10"):
        bob.list_messages(max_results=2)


def test_send_receive(alice: MeshClient, bob: MeshClient):
    message_id = alice.send_message(bob_mailbox, b"Hello Bob 1", workflow_id=uuid4().hex)
    assert bob.list_messages() == [message_id]
    assert bob.count_messages() == 1
    msg = bob.retrieve_message(message_id)
    assert msg.read() == b"Hello Bob 1"
    assert msg.sender == "ALICE"
    assert msg.recipient == "BOB"
    assert msg.content_type == "application/octet-stream"
    msg.acknowledge()
    assert bob.list_messages() == []


def test_send_receive_combine_streams_part1_multiple_of_chunk_size(alice: MeshClient, bob: MeshClient):
    part1_length = 10
    part2_length = 23

    stream = {
        "Body": CombineStreams([io.BytesIO(b"H" * part1_length), io.BytesIO(b"W" * part2_length)]),
        "ContentLength": part1_length + part2_length,
    }

    message_id = alice.send_message(bob_mailbox, stream, workflow_id=uuid4().hex)
    assert bob.list_messages() == [message_id]
    assert bob.count_messages() == 1
    msg = bob.retrieve_message(message_id)
    assert msg.read() == b"H" * part1_length + b"W" * part2_length
    assert msg.sender == "ALICE"
    assert msg.recipient == "BOB"
    msg.acknowledge()
    assert bob.list_messages() == []


def test_send_receive_combine_chunked_small_chunk_size(alice: MeshClient, bob: MeshClient):
    part1_length = 4
    part2_length = 20

    stream = {
        "Body": CombineStreams([io.BytesIO(b"H" * part1_length), io.BytesIO(b"W" * part2_length)]),
        "ContentLength": part1_length + part2_length,
    }

    message_id = alice.send_message(bob_mailbox, stream, workflow_id=uuid4().hex)
    assert bob.list_messages() == [message_id]
    assert bob.count_messages() == 1
    msg = bob.retrieve_message(message_id)
    assert msg.mex_header("chunk-range") == "1:5"


def test_send_receive_combine_chunked_override_chunk_size(alice: MeshClient, bob: MeshClient):
    part1_length = 4
    part2_length = 20

    stream = {
        "Body": CombineStreams([io.BytesIO(b"H" * part1_length), io.BytesIO(b"W" * part2_length)]),
        "ContentLength": part1_length + part2_length,
    }

    message_id = alice.send_message(bob_mailbox, stream, max_chunk_size=1, workflow_id=uuid4().hex)
    assert bob.list_messages() == [message_id]
    assert bob.count_messages() == 1
    msg = bob.retrieve_message(message_id)
    assert msg.mex_header("chunk-range") == "1:24"


def test_send_receive_combine_streams_part1_not_multiple_of_chunk_size(alice: MeshClient, bob: MeshClient):
    part1_length = 4
    part2_length = 20

    stream = {
        "Body": CombineStreams([io.BytesIO(b"H" * part1_length), io.BytesIO(b"W" * part2_length)]),
        "ContentLength": part1_length + part2_length,
    }

    message_id = alice.send_message(bob_mailbox, stream, workflow_id=uuid4().hex)
    assert bob.list_messages() == [message_id]
    assert bob.count_messages() == 1
    msg = bob.retrieve_message(message_id)
    assert msg.read() == b"H" * part1_length + b"W" * part2_length
    assert msg.sender == "ALICE"
    assert msg.recipient == "BOB"
    msg.acknowledge()
    assert bob.list_messages() == []


def test_line_by_line(alice: MeshClient, bob: MeshClient):
    message_id = alice.send_message(bob_mailbox, b"Hello Bob 1\nHello Bob 2", workflow_id=uuid4().hex)
    assert bob.list_messages() == [message_id]
    msg = bob.retrieve_message(message_id)
    assert list(iter(msg)) == [b"Hello Bob 1\n", b"Hello Bob 2"]


def test_readline(alice: MeshClient, bob: MeshClient):
    message_id = alice.send_message(bob_mailbox, b"Hello Bob 1\nHello Bob 2", workflow_id=uuid4().hex)
    assert bob.list_messages() == [message_id]
    msg = bob.retrieve_message(message_id)
    assert msg.readline() == b"Hello Bob 1\n"


def test_readlines(alice: MeshClient, bob: MeshClient):
    message_id = alice.send_message(bob_mailbox, b"Hello Bob 1\nHello Bob 2", workflow_id=uuid4().hex)
    assert bob.list_messages() == [message_id]
    msg = bob.retrieve_message(message_id)
    assert msg.readlines() == [b"Hello Bob 1\n", b"Hello Bob 2"]


def test_transparent_compression(alice: MeshClient, bob: MeshClient):
    print("Sending")
    alice._transparent_compress = True
    message_id = alice.send_message(bob_mailbox, b"Hello Bob Compressed", workflow_id=uuid4().hex)
    assert bob.list_messages() == [message_id]
    print("Receiving")
    msg = bob.retrieve_message(message_id)
    assert msg.read() == b"Hello Bob Compressed"
    assert msg.mex_header("from") == "ALICE"
    msg.acknowledge()
    assert bob.list_messages() == []


def test_iterate_and_context_manager(alice: MeshClient, bob: MeshClient):
    alice.send_message(bob_mailbox, b"Hello Bob 2", workflow_id=uuid4().hex)
    alice.send_message(bob_mailbox, b"Hello Bob 3", workflow_id=uuid4().hex)
    messages_read = 0
    for msg, expected in zip(bob.iterate_all_messages(), [b"Hello Bob 2", b"Hello Bob 3"]):
        with msg:
            assert msg.read() == expected
            messages_read += 1
    assert messages_read == 2
    assert bob.list_messages() == []


def test_context_manager_failure(alice: MeshClient, bob: MeshClient):
    message_id = alice.send_message(bob_mailbox, b"Hello Bob 4", workflow_id=uuid4().hex)
    try:
        with bob.retrieve_message(message_id) as msg:
            assert msg.read() == b"Hello Bob 4"
            raise TestError
    except TestError:
        pass
    assert bob.list_messages() == [message_id]


def test_optional_args(alice: MeshClient, bob: MeshClient):
    message_id = alice.send_message(
        bob_mailbox,
        b"Hello Bob 5",
        subject="Hello World",
        filename="upload.txt",
        local_id="12345",
        message_type="DATA",
        workflow_id="111",
        encrypted=False,
        compressed=False,
    )

    with bob.retrieve_message(message_id) as msg:
        assert msg.subject == "Hello World"
        assert msg.filename == "upload.txt"
        assert msg.local_id == "12345"
        assert msg.message_type == "DATA"
        assert msg.workflow_id == "111"
        assert msg.encrypted is False

    message_id = alice.send_message(
        bob_mailbox, b"Hello Bob 5", encrypted=True, compressed=True, workflow_id=uuid4().hex
    )

    with bob.retrieve_message(message_id) as msg:
        assert msg.encrypted is True
        assert msg.compressed is True


def test_msg_id_tracking_message_not_found(alice: MeshClient, bob: MeshClient):
    with pytest.raises(HTTPError) as err:
        assert alice.track_message(message_id=uuid4().hex)
    assert err.value.response is not None
    assert err.value.response.status_code == 404


def test_msg_id_tracking(alice: MeshClient, bob: MeshClient):
    msg_id = alice.send_message(bob_mailbox, b"Hello World", workflow_id=uuid4().hex)
    assert alice.track_message(message_id=msg_id)["status"] == "accepted"
    bob.acknowledge_message(msg_id)
    assert alice.track_message(message_id=msg_id)["status"] == "acknowledged"


def test_endpoint_lookup(alice: MeshClient, bob: MeshClient):
    result = alice.lookup_endpoint("X26", "RESTRICTED_WORKFLOW")
    result_list = cast(List[dict], result["results"])
    assert len(result_list) == 1
    assert result_list[0]["mailbox_id"] == "BOB"
    assert result_list[0]["mailbox_name"] == "TESTMB2"


def test_error_handling(alice: MeshClient, bob: MeshClient):
    with pytest.raises(MeshError):
        alice.send_message(bob_mailbox, b"")
