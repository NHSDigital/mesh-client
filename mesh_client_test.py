from unittest import TestCase, main
import os
from mesh_client import MeshClient, default_client_context
from mesh_client.mock_server import MockMeshApplication


alice_mailbox = 'alice'
alice_password = 'password'
bob_mailbox = 'bob'
bob_password = 'password'


class TestError(StandardError):
    pass


class MeshClientTest(TestCase):
    def test_send_receive(self):
        with MockMeshApplication() as mock_app:
            uri = mock_app.uri
            alice = MeshClient(uri, alice_mailbox, alice_password,
                               ssl_context=default_client_context)
            bob = MeshClient(uri, bob_mailbox, bob_password,
                             ssl_context=default_client_context)

            message_id = alice.send_message(bob_mailbox, b"Hello Bob 1")
            self.assertEqual([message_id], bob.list_messages())
            msg = bob.retrieve_message(message_id)
            self.assertEqual(msg.read(), b"Hello Bob 1")
            msg.acknowledge()
            self.assertEqual([], bob.list_messages())

    def test_iterate_and_context_manager(self):
        with MockMeshApplication() as mock_app:
            uri = mock_app.uri
            alice = MeshClient(uri, alice_mailbox, alice_password,
                               ssl_context=default_client_context)
            bob = MeshClient(uri, bob_mailbox, bob_password,
                             ssl_context=default_client_context)

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
        with MockMeshApplication() as mock_app:
            uri = mock_app.uri
            alice = MeshClient(uri, alice_mailbox, alice_password,
                               ssl_context=default_client_context)
            bob = MeshClient(uri, bob_mailbox, bob_password,
                             ssl_context=default_client_context)

            message_id = alice.send_message(bob_mailbox, b"Hello Bob 4")
            try:
                with bob.retrieve_message(message_id) as msg:
                    self.assertEqual(msg.read(), b"Hello Bob 4")
                    raise TestError()
            except TestError:
                pass
            self.assertEqual([message_id], bob.list_messages())


if __name__ == "__main__":
    main()
