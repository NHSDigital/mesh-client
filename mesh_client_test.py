from __future__ import absolute_import, print_function

import io
from unittest import TestCase, main
import mock
import requests
import signal
import traceback
import sys

from collections import namedtuple
from mesh_client import MeshClient, MeshError, default_ssl_opts, CombineStreams, LOCAL_MOCK_ENDPOINT
from mesh_client.mock_server import MockMeshApplication, MockMeshChunkRetryApplication
from six.moves.urllib.error import HTTPError

alice_mailbox = 'alice'
alice_password = 'password'
bob_mailbox = 'bob'
bob_password = 'password'

unmocked_post = requests.post


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


class MeshClientTest(TestCase):
    def run(self, result=None):
        try:
            with MockMeshApplication() as mock_app:
                self.mock_app = mock_app
                self.uri = mock_app.uri
                self.alice = MeshClient(
                    self.uri,
                    alice_mailbox,
                    alice_password,
                    max_chunk_size=5,
                    **default_ssl_opts)
                self.bob = MeshClient(
                    self.uri,
                    bob_mailbox,
                    bob_password,
                    max_chunk_size=5,
                    **default_ssl_opts)
                super(MeshClientTest, self).run(result)
        except HTTPError as e:
            print(e.read())
            print_stack_frames()
            print("Message store", self.mock_app.messages)
            raise
        except:
            print_stack_frames()
            print("Message store", self.mock_app.messages)
            raise

    def test_handshake(self):
        alice = self.alice

        hand_shook = alice.handshake()
        self.assertEqual(hand_shook, b"hello")

    def test_send_receive(self):
        alice = self.alice
        bob = self.bob

        message_id = alice.send_message(bob_mailbox, b"Hello Bob 1")
        self.assertEqual([message_id], bob.list_messages())
        self.assertEqual(1, bob.count_messages())
        msg = bob.retrieve_message(message_id)
        self.assertEqual(msg.read(), b"Hello Bob 1")
        self.assertEqual(msg.sender, "alice")
        self.assertEqual(msg.recipient, "bob")
        msg.acknowledge()
        self.assertEqual([], bob.list_messages())

    def test_send_receive_combine_streams_part1_multiple_of_chunk_size(self):
        alice = self.alice
        bob = self.bob

        part1_length = 10
        part2_length = 23

        stream = {
            'Body': CombineStreams([io.BytesIO(b"H"*part1_length), io.BytesIO((b"W"*part2_length))]),
            'ContentLength': part1_length + part2_length,
        }

        message_id = alice.send_message(bob_mailbox, stream)
        self.assertEqual([message_id], bob.list_messages())
        self.assertEqual(1, bob.count_messages())
        msg = bob.retrieve_message(message_id)
        self.assertEqual(msg.read(), b"H" * part1_length + b"W"*part2_length)
        self.assertEqual(msg.sender, "alice")
        self.assertEqual(msg.recipient, "bob")
        msg.acknowledge()
        self.assertEqual([], bob.list_messages())

    def test_send_receive_combine_streams_part1_not_multiple_of_chunk_size(self):
        alice = self.alice
        bob = self.bob

        part1_length = 4
        part2_length = 20

        stream = {
            'Body': CombineStreams([io.BytesIO(b"H"*part1_length), io.BytesIO((b"W"*part2_length))]),
            'ContentLength': part1_length + part2_length,
        }

        message_id = alice.send_message(bob_mailbox, stream)
        self.assertEqual([message_id], bob.list_messages())
        self.assertEqual(1, bob.count_messages())
        msg = bob.retrieve_message(message_id)
        self.assertEqual(msg.read(), b"H" * part1_length + b"W"*part2_length)
        self.assertEqual(msg.sender, "alice")
        self.assertEqual(msg.recipient, "bob")
        msg.acknowledge()
        self.assertEqual([], bob.list_messages())

    def test_line_by_line(self):
        alice = self.alice
        bob = self.bob

        message_id = alice.send_message(bob_mailbox, b"Hello Bob 1\nHello Bob 2")
        self.assertEqual([message_id], bob.list_messages())
        msg = bob.retrieve_message(message_id)
        self.assertEqual(list(iter(msg)), [b"Hello Bob 1\n", b"Hello Bob 2"])

    def test_readline(self):
        alice = self.alice
        bob = self.bob

        message_id = alice.send_message(bob_mailbox, b"Hello Bob 1\nHello Bob 2")
        self.assertEqual([message_id], bob.list_messages())
        msg = bob.retrieve_message(message_id)
        self.assertEqual(msg.readline(), b"Hello Bob 1\n")

    def test_readlines(self):
        alice = self.alice
        bob = self.bob

        message_id = alice.send_message(bob_mailbox, b"Hello Bob 1\nHello Bob 2")
        self.assertEqual([message_id], bob.list_messages())
        msg = bob.retrieve_message(message_id)
        self.assertEqual(msg.readlines(), [b"Hello Bob 1\n", b"Hello Bob 2"])

    def test_transparent_compression(self):
        alice = self.alice
        bob = self.bob

        print("Sending")
        alice._transparent_compress = True
        message_id = alice.send_message(
            bob_mailbox, b"Hello Bob Compressed")
        self.assertEqual([message_id], bob.list_messages())
        print("Receiving")
        msg = bob.retrieve_message(message_id)
        self.assertEqual(msg.read(), b"Hello Bob Compressed")
        self.assertEqual(msg.mex_header('from'), 'alice')
        msg.acknowledge()
        self.assertEqual([], bob.list_messages())

    def test_iterate_and_context_manager(self):
        alice = self.alice
        bob = self.bob

        alice.send_message(bob_mailbox, b"Hello Bob 2")
        alice.send_message(bob_mailbox, b"Hello Bob 3")
        messages_read = 0
        for (msg, expected) in zip(bob.iterate_all_messages(),
                                   [b"Hello Bob 2", b"Hello Bob 3"]):
            with msg:
                self.assertEqual(msg.read(), expected)
                messages_read += 1
        self.assertEqual(2, messages_read)
        self.assertEqual([], bob.list_messages())

    def test_context_manager_failure(self):
        alice = self.alice
        bob = self.bob

        message_id = alice.send_message(bob_mailbox, b"Hello Bob 4")
        try:
            with bob.retrieve_message(message_id) as msg:
                self.assertEqual(msg.read(), b"Hello Bob 4")
                raise TestError()
        except TestError:
            pass
        self.assertEqual([message_id], bob.list_messages())

    def test_optional_args(self):
        alice = self.alice
        bob = self.bob

        message_id = alice.send_message(
            bob_mailbox,
            b"Hello Bob 5",
            subject="Hello World",
            filename="upload.txt",
            local_id="12345",
            message_type="DATA",
            process_id="321",
            workflow_id="111",
            encrypted=False,
            compressed=False)

        with bob.retrieve_message(message_id) as msg:
            self.assertEqual(msg.subject, "Hello World")
            self.assertEqual(msg.filename, "upload.txt")
            self.assertEqual(msg.local_id, "12345")
            self.assertEqual(msg.message_type, "DATA")
            self.assertEqual(msg.process_id, "321")
            self.assertEqual(msg.workflow_id, "111")
            self.assertFalse(msg.encrypted)
            self.assertFalse(msg.compressed)

        message_id = alice.send_message(
            bob_mailbox, b"Hello Bob 5", encrypted=True, compressed=True)

        with bob.retrieve_message(message_id) as msg:
            self.assertTrue(msg.encrypted)
            self.assertTrue(msg.compressed)

    def test_tracking(self):
        alice = self.alice
        bob = self.bob
        tracking_id = 'Message1'
        msg_id = alice.send_message(bob_mailbox, b'Hello World', local_id=tracking_id)
        self.assertEqual(alice.get_tracking_info(tracking_id)['status'], 'Accepted')
        bob.acknowledge_message(msg_id)
        self.assertEqual(alice.get_tracking_info(tracking_id)['status'], 'Acknowledged')

    def test_error_handling(self):
        alice = self.alice
        with self.assertRaises(MeshError):
            alice.send_message(bob_mailbox, b"")


class EndpointTest(TestCase):
    def test_handshake(self):
        with MockMeshApplication() as mock_app:
            endpoint = LOCAL_MOCK_ENDPOINT._replace(url=mock_app.uri)
            client = MeshClient(
                endpoint,
                alice_mailbox,
                alice_password,
                max_chunk_size=5)

            hand_shook = client.handshake()
            self.assertEqual(hand_shook, b"hello")


class MeshChunkRetryClientTest(TestCase):
    def run(self, result=None):
        self.chunk_retry_call_counts = {}
        try:
            with  MockMeshChunkRetryApplication() as mock_app:
                self.mock_app = mock_app
                self.uri = mock_app.uri
                self.alice = MeshClient(
                    self.uri,
                    alice_mailbox,
                    alice_password,
                    max_chunk_size=5,
                    max_chunk_retries=3,
                    **default_ssl_opts)
                self.bob = MeshClient(
                    self.uri,
                    bob_mailbox,
                    bob_password,
                    max_chunk_size=5,
                    max_chunk_retries=3,
                    **default_ssl_opts)
                super(MeshChunkRetryClientTest, self).run(result)
        except HTTPError as e:
            print(e.read())
            print_stack_frames()
            print("Message store", self.mock_app.messages)
            raise
        except:
            print_stack_frames()
            print("Message store", self.mock_app.messages)
            raise

    def wrapped_post(self, url, data, **kwargs):
        current_chunk = int(kwargs['headers']['Mex-Chunk-Range'].split(':')[0])
        if current_chunk not in self.chunk_retry_call_counts.keys():
            self.chunk_retry_call_counts[current_chunk] = 0
        else:
            self.chunk_retry_call_counts[current_chunk] += 1

        response = unmocked_post(url, data, **kwargs)
        return response

    @mock.patch('requests.post')
    def test_chunk_retries(self, mock_post):
        mock_post.side_effect = self.wrapped_post

        alice = self.alice
        bob = self.bob

        chunk_options = namedtuple('Chunk', 'chunk_num num_retry_attempts')
        options = [chunk_options(2, 2)]
        self.mock_app.set_chunk_retry_options(options)

        message_id = alice.send_message(bob_mailbox, b"Hello World")

        received = bob.retrieve_message(message_id).read()
        self.assertEqual(received, b'Hello World')

        self.assertEqual(self.chunk_retry_call_counts[1], 0)
        self.assertEqual(self.chunk_retry_call_counts[2], 3)
        self.assertEqual(self.chunk_retry_call_counts[3], 0)

    @mock.patch('requests.post')
    def test_chunk_all_retries_fail(self, mock_post):
        mock_post.side_effect = self.wrapped_post

        alice = self.alice

        chunk_options = namedtuple('Chunk', 'chunk_num num_retry_attempts')
        options = [chunk_options(2, 3)]
        self.mock_app.set_chunk_retry_options(options)

        self.assertRaises(requests.exceptions.HTTPError, alice.send_message, bob_mailbox, b"Hello World")

        self.assertEqual(self.chunk_retry_call_counts[1], 0)
        self.assertEqual(self.chunk_retry_call_counts[2], 3)

    @mock.patch('requests.post')
    def test_chunk_retries_with_file(self, mock_post):
        mock_post.side_effect = self.wrapped_post

        alice = self.alice
        bob = self.bob

        chunk_options = namedtuple('Chunk', 'chunk_num num_retry_attempts')
        options = [chunk_options(2, 2)]
        self.mock_app.set_chunk_retry_options(options)

        message_id = alice.send_message(bob_mailbox, open("test_chunk_retry_file", 'rb'))

        received = bob.retrieve_message(message_id).read()
        self.assertEqual(received, b'test1 test2 test3')

        self.assertEqual(self.chunk_retry_call_counts[1], 0)
        self.assertEqual(self.chunk_retry_call_counts[2], 3)
        self.assertEqual(self.chunk_retry_call_counts[3], 0)


if __name__ == "__main__":
    main()
