from __future__ import absolute_import, print_function
from unittest import TestCase, main
import signal
import traceback
import sys
from mesh_client import MeshClient, MeshError, default_ssl_opts
from mesh_client.mock_server import MockMeshApplication
from six.moves.urllib.error import HTTPError

alice_mailbox = 'alice'
alice_password = 'password'
bob_mailbox = 'bob'
bob_password = 'password'


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

    def test_send_receive(self):
        alice = self.alice
        bob = self.bob

        message_id = alice.send_message(bob_mailbox, b"Hello Bob 1")
        self.assertEqual([message_id], bob.list_messages())
        msg = bob.retrieve_message(message_id)
        self.assertEqual(msg.read(), b"Hello Bob 1")
        self.assertEqual(msg.sender, "alice")
        self.assertEqual(msg.recipient, "bob")
        msg.acknowledge()
        self.assertEqual([], bob.list_messages())

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

    def test_error_handling(self):
        alice = self.alice
        with self.assertRaises(MeshError):
            alice.send_message(bob_mailbox, b"")


if __name__ == "__main__":
    main()
