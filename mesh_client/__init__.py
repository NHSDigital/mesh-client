import uuid
import hmac
import datetime
import os.path
import ssl
from six.moves.urllib.request import Request, urlopen
from contextlib import closing
import json
from hashlib import sha256


_data_dir = os.path.dirname(__file__)
default_client_context = ssl.create_default_context(
    ssl.Purpose.CLIENT_AUTH,
    cafile=os.path.join(_data_dir, "ca.cert.pem"))
default_client_context.load_cert_chain(
    os.path.join(_data_dir, 'client.cert.pem'),
    os.path.join(_data_dir, 'client.key.pem'))


class MeshClient(object):
    def __init__(self,
                 url,
                 mailbox,
                 password,
                 shared_key=b"BackBone",
                 ssl_context=None):
        self._url = url
        self._mailbox = mailbox
        self._ssl_context = ssl_context
        self._token_generator = _AuthTokenGenerator(shared_key, mailbox,
                                                    password)

    def list_messages(self):
        req = Request(
            "{}/messageexchange/{}/inbox".format(self._url, self._mailbox),
            headers={"Authorization": self._token_generator()})
        with closing(urlopen(req, context=self._ssl_context)) as resp:
            return json.loads(resp.read().decode("UTF-8"))["messages"]

    def retrieve_message(self, message_id):
        message_id = getattr(message_id, "_msg_id", message_id)
        req = Request(
            "{}/messageexchange/{}/inbox/{}".format(self._url, self._mailbox,
                                                    message_id),
            headers={"Authorization": self._token_generator()})
        return _Message(
            message_id, urlopen(
                req, context=self._ssl_context), self)

    def send_message(self, recipient, data):
        req = Request(
            "{}/messageexchange/{}/outbox".format(self._url, self._mailbox),
            data,
            headers={
                "Authorization": self._token_generator(),
                "Mex-From": self._mailbox,
                "Mex-To": recipient,
                "Mex-LocalID": self._mailbox
            })
        with closing(urlopen(req, context=self._ssl_context)) as resp:
            return json.load(resp)["messageID"]

    def acknowledge_message(self, message_id):
        message_id = getattr(message_id, "_msg_id", message_id)
        req = Request(
            "{}/messageexchange/{}/inbox/{}/status/acknowledged".format(
                self._url, self._mailbox, message_id),
            headers={
                "Authorization": self._token_generator(),
            })
        req.get_method = lambda: "PUT"
        with closing(urlopen(req, context=self._ssl_context)) as resp:
            return resp.read()

    def iterate_all_messages(self):
        for msg_id in self.list_messages():
            yield self.retrieve_message(msg_id)


class _Message(object):
    def __init__(self, msg_id, response, client):
        self._msg_id = msg_id
        self._response = response
        self._client = client

    def read(self, *args, **kwargs):
        return self._response.read(*args, **kwargs)

    def acknowledge(self):
        self._client.acknowledge_message(self._msg_id)

    def __enter__(self):
        return self

    def __exit__(self, typ, value, traceback):
        try:
            if not value:
                self.acknowledge()
        finally:
            self._response.close()


class _AuthTokenGenerator(object):
    def __init__(self, key, mailbox, password):
        self._key = key
        self._mailbox = mailbox
        self._password = password
        self._nonce = uuid.uuid4()
        self._nonce_count = 0

    def __call__(self):
        now = datetime.datetime.now().strftime("%Y%m%d%H%M")
        public_auth_data = _combine(self._mailbox, self._nonce,
                                    self._nonce_count, now)
        private_auth_data = _combine(self._mailbox, self._nonce,
                                     self._nonce_count, self._password, now)
        myhash = hmac.HMAC(self._key, private_auth_data.encode("ASCII"),
                           sha256).hexdigest()
        self._nonce_count += 1
        return "NHSMESH {public_auth_data}:{myhash}".format(**locals())


def _combine(*elements):
    return ":".join(str(x) for x in elements)
