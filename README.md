MESH Client
===========

A Python client for [NHS Digital's MESH API](https://digital.nhs.uk/developer/api-catalogue/message-exchange-for-social-care-and-health-api).

Installation
------------

```bash
pip install mesh-client
```

Example use
-----------

```python
from mesh_client import MeshClient, NHS_DEP_ENDPOINT
with MeshClient(
          NHS_DEP_ENDPOINT,
          'MYMAILBOX',
          'Password',
          cert=('/etc/certs/cert.pem', '/etc/certs/key.pem')  # Mesh uses SSL, so you'll need some certs
        ) as client:

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

Testing your application
------------------------

We recommend using the [mesh sandbox](https://github.com/NHSDigital/mesh-sandbox) 
have a look at this [docker-compose.yml](docker-compose.yml) for an example of how to run the sandbox


Guidance for contributors
-------------------------

see [CONTRIBUTING](CONTRIBUTING.md)

