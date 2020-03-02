MESH Client
===========

A Python client for [NHS Digital's MESH API](https://meshapi.docs.apiary.io/).

Installation
------------

```
pip install mesh_client
```

Example use
-----------

```
from mesh_client import MeshClient
client = MeshClient(
    'https://msg.dep.spine2.ncrs.nhs.uk',
    'MYMAILBOX',
    'Password123!'
    cert=('/etc/certs/cert.pem', '/etc/certs/key.pem'),  # Mesh uses SSL, so you'll need some certs
    verify='/etc/certs/mesh-ca-cert.pem')

client.handshake()  # It will work without this, but Spine will complain
message_ids = client.list_messages()
first_message = client.retrieve_message(message_ids[0])
print('Subject', first_message.subject)
print('Message', first_message.read())
first_message.acknowledge()

# Alternatively, iterate
for message in client.iterate_all_messages():
    with message: # With block will handle acknowledgement
        print('Message', message.read())

client.send_message('RECIPIENT_MAILBOX', b'Hello World!', subject='Important message')
```
