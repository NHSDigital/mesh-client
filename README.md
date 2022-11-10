MESH Client
===========

A Python client for [NHS Digital's MESH API](https://digital.nhs.uk/developer/api-catalogue/message-exchange-for-social-care-and-health-api).

Installation
------------

```bash
pip install mesh_client
```

Example use
-----------

```python
from mesh_client import MeshClient, NHS_DEP_ENDPOINT
with MeshClient(
          NHS_DEP_ENDPOINT,
          'MYMAILBOX',
          'Password123!',
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

Guidance for contributors
-------------------------

You should be doing all your development in a virtualenv / venv. You can install
everything you need for development with

```bash
virtualenv .venv
source .venv/bin/activate
pip install -r dev-requirements.txt
pip install -e .

# if using asdf
pip install tox-asdf

```

We use unittest for tests, and you can run the test suite locally with:

```bash
python -m unittest discover . '*_test.py'
```

We use tox for testing on multiple versions. To run the tox tests, just run:

```bash
tox
```

For releases, we use twine. The rough release process would be:

```bash
tox  # Re-run tests, just to be sure
git tag $CURRENT_VERSION
rm dist/*  # Get rid of previous distribution files
python -m build
twine upload -r testpypi dist/*
# Check artifacts are uploaded correctly, and that entry on PyPI looks correct
twine upload dist/*
git push --tags
```
