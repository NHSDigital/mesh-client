from unittest import TestCase, main
import os
from mesh_client import MeshClient, MeshError, default_client_context
from mesh_client.mock_server import MockMeshApplication
from six.moves.urllib.error import HTTPError


alice_mailbox = 'alice'
alice_password = 'password'
bob_mailbox = 'bob'
bob_password = 'password'


class TestError(StandardError):
    pass


class MeshClientTest(TestCase):
    def run(self, result=None):
        try:
            with MockMeshApplication() as mock_app:
                self.mock_app = mock_app
                self.uri = mock_app.uri
                self.alice = MeshClient(self.uri, alice_mailbox, alice_password,
                                        ssl_context=default_client_context)
                self.bob = MeshClient(self.uri, bob_mailbox, bob_password,
                                      ssl_context=default_client_context)
                super(MeshClientTest, self).run(result)
        except HTTPError as e:
            print e.read()
            raise

    def test_send_receive(self):
        alice = self.alice
        bob = self.bob

        message_id = alice.send_message(bob_mailbox, b"Hello Bob 1")
        self.assertEqual([message_id], bob.list_messages())
        msg = bob.retrieve_message(message_id)
        self.assertEqual(msg.read(), b"Hello Bob 1")
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
            bob_mailbox, b"Hello Bob 5",
            subject="Hello World",
            content_type="text/plain; charset=ascii",
            filename="upload.txt",
            local_id="12345",
            message_type="DATA",
            process_id="321",
            workflow_id="111",
            encrypted=False,
            compressed=False
        )

        with bob.retrieve_message(message_id) as msg:
            self.assertEqual(msg.subject, "Hello World")
            self.assertEqual(msg.content_type, "text/plain; charset=ascii")
            self.assertEqual(msg.filename, "upload.txt")
            self.assertEqual(msg.local_id, "12345")
            self.assertEqual(msg.message_type, "DATA")
            self.assertEqual(msg.process_id, "321")
            self.assertEqual(msg.workflow_id, "111")
            self.assertEqual(msg.encrypted, "False")
            self.assertEqual(msg.compressed, "False")

    def test_error_handling(self):
        alice = self.alice
        with self.assertRaises(MeshError):
            alice.send_message(bob_mailbox, b"")

if __name__ == "__main__":
    main()
