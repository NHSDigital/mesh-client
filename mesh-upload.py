#!/usr/bin/python3
import ssl
import traceback
from mesh_client import MeshClient

#_host = "https://mesh-sync.national.ncrs.nhs.uk"
_host = "https://localhost:8000"

_ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH, cafile="ca.cert.pem")
_ssl_context.load_cert_chain('client.cert.pem', 'client.key.pem')

_alice_mailbox = "alice"
_bob_mailbox = "bob"
_password = "password"

if __name__ == "__main__":
    try:
        alice = MeshClient(_host, _alice_mailbox, _password, ssl_context=_ssl_context)
        bob = MeshClient(_host, _bob_mailbox, _password, ssl_context=_ssl_context)

        print("Sending from Alice to Bob")
        print(alice.send_message(_bob_mailbox, b"Hello Bob"))
        print("Receiving Bob's messages")
        print(bob.list_messages())
        for msg in bob.iterate_all_messages():
            with msg:
                print(msg.read())
        print(bob.list_messages())

        # print("Sending from Bob to Alice")
        # print(bob.send_message(_alice_mailbox, b"Hello Alice"))
        # print("Receiving Alice's messages")
        # print(alice.list_messages())
        # for msg in alice.list_messages():
        #     print(msg.content)
        #     msg.acknowledge()
        #     print ("message {} deleted".format(msg.id))


    except Exception as e:
        traceback.print_exc()
        print(e.read())
