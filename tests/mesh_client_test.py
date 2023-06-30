import io
import signal
import sys
import traceback

import pytest
import requests

from mesh_client import (
    LOCAL_MOCK_ENDPOINT,
    CombineStreams,
    MeshClient,
    MeshError,
    default_ssl_opts,
)
from mesh_client.mock_server import MockMeshApplication, SlowMockMeshApplication

alice_mailbox = "alice"
alice_password = "password"
bob_mailbox = "bob"
bob_password = "password"


class MockResponse:
    def __init__(self, json_data, status_code):
        self.json_data = json_data
        self.status_code = status_code

    def json(self):
        return self.json_data


def print_stack_frames(signum=None, frame=None):
    for frame in sys._current_frames().values():
        traceback.print_stack(frame)
        print()


signal.signal(signal.SIGUSR1, print_stack_frames)


class TestError(Exception):
    pass


@pytest.fixture(scope="function", name="mock_app")
def _mock_mesh_app():
    with MockMeshApplication() as mock_app:
        yield mock_app


@pytest.fixture(scope="function", name="alice")
def _alice_mesh_client(mock_app: MockMeshApplication):
    with MeshClient(mock_app.uri, alice_mailbox, alice_password, max_chunk_size=5, **default_ssl_opts) as alice:
        yield alice


@pytest.fixture(scope="function", name="bob")
def _bob_mesh_client(mock_app: MockMeshApplication):
    with MeshClient(mock_app.uri, bob_mailbox, bob_password, max_chunk_size=5, **default_ssl_opts) as bob:
        yield bob


def test_handshake(alice: MeshClient, bob: MeshClient):
    hand_shook = alice.handshake()
    assert hand_shook == b"hello"


def test_send_receive(alice: MeshClient, bob: MeshClient):
    message_id = alice.send_message(bob_mailbox, b"Hello Bob 1")
    assert bob.list_messages() == [message_id]
    assert bob.count_messages() == 1
    msg = bob.retrieve_message(message_id)
    assert msg.read() == b"Hello Bob 1"
    assert msg.sender == "alice"
    assert msg.recipient == "bob"
    msg.acknowledge()
    assert bob.list_messages() == []


def test_send_receive_combine_streams_part1_multiple_of_chunk_size(alice: MeshClient, bob: MeshClient):
    part1_length = 10
    part2_length = 23

    stream = {
        "Body": CombineStreams([io.BytesIO(b"H" * part1_length), io.BytesIO((b"W" * part2_length))]),
        "ContentLength": part1_length + part2_length,
    }

    message_id = alice.send_message(bob_mailbox, stream)
    assert bob.list_messages() == [message_id]
    assert bob.count_messages() == 1
    msg = bob.retrieve_message(message_id)
    assert msg.read() == b"H" * part1_length + b"W" * part2_length
    assert msg.sender == "alice"
    assert msg.recipient == "bob"
    msg.acknowledge()
    assert bob.list_messages() == []


def test_send_receive_combine_chunked_small_chunk_size(alice: MeshClient, bob: MeshClient):
    part1_length = 4
    part2_length = 20

    stream = {
        "Body": CombineStreams([io.BytesIO(b"H" * part1_length), io.BytesIO((b"W" * part2_length))]),
        "ContentLength": part1_length + part2_length,
    }

    message_id = alice.send_message(bob_mailbox, stream)
    assert bob.list_messages() == [message_id]
    assert bob.count_messages() == 1
    msg = bob.retrieve_message(message_id)
    assert msg.mex_header("chunk-range") == "1:5"


def test_send_receive_combine_chunked_override_chunk_size(alice: MeshClient, bob: MeshClient):
    part1_length = 4
    part2_length = 20

    stream = {
        "Body": CombineStreams([io.BytesIO(b"H" * part1_length), io.BytesIO((b"W" * part2_length))]),
        "ContentLength": part1_length + part2_length,
    }

    message_id = alice.send_message(bob_mailbox, stream, max_chunk_size=1)
    assert bob.list_messages() == [message_id]
    assert bob.count_messages() == 1
    msg = bob.retrieve_message(message_id)
    assert msg.mex_header("chunk-range") == "1:24"


def test_send_receive_combine_streams_part1_not_multiple_of_chunk_size(alice: MeshClient, bob: MeshClient):
    part1_length = 4
    part2_length = 20

    stream = {
        "Body": CombineStreams([io.BytesIO(b"H" * part1_length), io.BytesIO((b"W" * part2_length))]),
        "ContentLength": part1_length + part2_length,
    }

    message_id = alice.send_message(bob_mailbox, stream)
    assert bob.list_messages() == [message_id]
    assert bob.count_messages() == 1
    msg = bob.retrieve_message(message_id)
    assert msg.read() == b"H" * part1_length + b"W" * part2_length
    assert msg.sender == "alice"
    assert msg.recipient == "bob"
    msg.acknowledge()
    assert bob.list_messages() == []


def test_line_by_line(alice: MeshClient, bob: MeshClient):
    message_id = alice.send_message(bob_mailbox, b"Hello Bob 1\nHello Bob 2")
    assert bob.list_messages() == [message_id]
    msg = bob.retrieve_message(message_id)
    assert list(iter(msg)) == [b"Hello Bob 1\n", b"Hello Bob 2"]


def test_readline(alice: MeshClient, bob: MeshClient):
    message_id = alice.send_message(bob_mailbox, b"Hello Bob 1\nHello Bob 2")
    assert bob.list_messages() == [message_id]
    msg = bob.retrieve_message(message_id)
    assert msg.readline() == b"Hello Bob 1\n"


def test_readlines(alice: MeshClient, bob: MeshClient):
    message_id = alice.send_message(bob_mailbox, b"Hello Bob 1\nHello Bob 2")
    assert bob.list_messages() == [message_id]
    msg = bob.retrieve_message(message_id)
    assert msg.readlines() == [b"Hello Bob 1\n", b"Hello Bob 2"]


def test_transparent_compression(alice: MeshClient, bob: MeshClient):
    print("Sending")
    alice._transparent_compress = True
    message_id = alice.send_message(bob_mailbox, b"Hello Bob Compressed")
    assert bob.list_messages() == [message_id]
    print("Receiving")
    msg = bob.retrieve_message(message_id)
    assert msg.read() == b"Hello Bob Compressed"
    assert msg.mex_header("from") == "alice"
    msg.acknowledge()
    assert bob.list_messages() == []


def test_iterate_and_context_manager(alice: MeshClient, bob: MeshClient):
    alice.send_message(bob_mailbox, b"Hello Bob 2")
    alice.send_message(bob_mailbox, b"Hello Bob 3")
    messages_read = 0
    for msg, expected in zip(bob.iterate_all_messages(), [b"Hello Bob 2", b"Hello Bob 3"]):
        with msg:
            assert msg.read() == expected
            messages_read += 1
    assert messages_read == 2
    assert bob.list_messages() == []


def test_context_manager_failure(alice: MeshClient, bob: MeshClient):
    message_id = alice.send_message(bob_mailbox, b"Hello Bob 4")
    try:
        with bob.retrieve_message(message_id) as msg:
            assert msg.read() == b"Hello Bob 4"
            raise TestError()
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
        assert msg.compressed is False

    message_id = alice.send_message(bob_mailbox, b"Hello Bob 5", encrypted=True, compressed=True)

    with bob.retrieve_message(message_id) as msg:
        assert msg.encrypted is True
        assert msg.compressed is True


def test_tracking(alice: MeshClient, bob: MeshClient):
    tracking_id = "Message1"
    msg_id = alice.send_message(bob_mailbox, b"Hello World", local_id=tracking_id)
    assert alice.get_tracking_info(tracking_id)["status"] == "Accepted"
    bob.acknowledge_message(msg_id)
    assert alice.get_tracking_info(tracking_id)["status"] == "Acknowledged"


def test_msg_id_tracking(alice: MeshClient, bob: MeshClient):
    msg_id = alice.send_message(bob_mailbox, b"Hello World")
    assert alice.get_tracking_info(message_id=msg_id)["status"] == "Accepted"
    bob.acknowledge_message(msg_id)
    assert alice.get_tracking_info(message_id=msg_id)["status"] == "Acknowledged"


def test_by_message_id_tracking(alice: MeshClient, bob: MeshClient):
    msg_id = alice.send_message(bob_mailbox, b"Hello World")
    assert alice.track_by_message_id(message_id=msg_id)["status"] == "Accepted"
    bob.acknowledge_message(msg_id)
    assert alice.track_by_message_id(message_id=msg_id)["status"] == "Acknowledged"


def test_endpoint_lookup(alice: MeshClient, bob: MeshClient):
    result = alice.lookup_endpoint("ORG1", "WF1")
    result_list = result["results"]
    assert len(result_list) == 1
    assert result_list[0]["address"] == "ORG1HC001"
    assert result_list[0]["description"] == "ORG1 WF1 endpoint"
    assert result_list[0]["endpoint_type"] == "MESH"


def test_error_handling(alice: MeshClient, bob: MeshClient):
    with pytest.raises(MeshError):
        alice.send_message(bob_mailbox, b"")


def test_timeout():
    with SlowMockMeshApplication() as mock_app:
        endpoint = LOCAL_MOCK_ENDPOINT._replace(url=mock_app.uri)
        client = MeshClient(endpoint, alice_mailbox, alice_password, max_chunk_size=5, timeout=0.5)
        with pytest.raises(requests.exceptions.Timeout):
            client.list_messages()
