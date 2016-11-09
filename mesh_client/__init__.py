from __future__ import absolute_import
import codecs
import uuid
import hmac
import datetime
import os.path
import requests
import ssl
import six
from itertools import chain
import json
from hashlib import sha256
from .io_helpers import CombineStreams, SplitStream, GzipCompressStream, GzipDecompressStream

_data_dir = os.path.dirname(__file__)

default_ssl_opts = {
    "verify": os.path.join(_data_dir, "ca.cert.pem"),
    "cert": (os.path.join(_data_dir, 'client.cert.pem'),
             os.path.join(_data_dir, 'client.key.pem'))
}

_OPTIONAL_HEADERS = {
    "workflow_id": "Mex-WorkflowID",
    "filename": "Mex-FileName",
    "local_id": "Mex-LocalID",
    "message_type": "Mex-MessageType",
    "process_id": "Mex-ProcessID",
    "subject": "Mex-Subject",
    "encrypted": "Mex-Encrypted",
    "compressed": "Mex-Compressed"
}

_utf8_reader = codecs.getreader("utf-8")


class MeshError(Exception):
    pass


class MeshClient(object):
    def __init__(self,
                 url,
                 mailbox,
                 password,
                 shared_key=b"BackBone",
                 ssl_context=None,
                 cert=None,
                 verify=None,
                 max_chunk_size=75 * 1024 * 1024):
        self._url = url
        self._mailbox = mailbox
        self._cert = cert
        self._verify = verify
        self._token_generator = _AuthTokenGenerator(shared_key, mailbox,
                                                    password)
        self._max_chunk_size = max_chunk_size

    def list_messages(self):
        response = requests.get(
            "{}/messageexchange/{}/inbox".format(self._url, self._mailbox),
            headers={"Authorization": self._token_generator()},
            cert=self._cert,
            verify=self._verify)
        return response.json()["messages"]

    def retrieve_message(self, message_id):
        message_id = getattr(message_id, "_msg_id", message_id)
        response = requests.get(
            "{}/messageexchange/{}/inbox/{}".format(self._url, self._mailbox,
                                                    message_id),
            headers={"Authorization": self._token_generator()},
            stream=True,
            cert=self._cert,
            verify=self._verify)
        return _Message(message_id, response, self)

    def retrieve_message_chunk(self, message_id, chunk_num):
        response = requests.get(
            "{}/messageexchange/{}/inbox/{}/{}".format(
                self._url, self._mailbox, message_id, chunk_num),
            headers={"Authorization": self._token_generator()},
            stream=True,
            cert=self._cert,
            verify=self._verify)
        return response.raw

    def send_message(self,
                     recipient,
                     data,
                     transparent_compress=False,
                     **kwargs):
        maybe_compressed = (
            lambda stream: GzipCompressStream(stream) if transparent_compress else stream
        )
        headers = {
            "Authorization": self._token_generator(),
            "Mex-From": self._mailbox,
            "Mex-To": recipient
        }
        for key, value in kwargs.items():
            if key in _OPTIONAL_HEADERS:
                headers[_OPTIONAL_HEADERS[key]] = str(value)
            else:
                raise TypeError("Unrecognised keyword argument {key}."
                                " optional arguments are: {args}".format(
                                    key=key,
                                    args=", ".join([
                                        "recipient", "data"
                                    ] + list(_OPTIONAL_HEADERS.keys()))))

        if transparent_compress:
            headers["Mex-Content-Compress"] = "TRUE"
            headers["Content-Encoding"] = "gzip"

        chunks = SplitStream(data, self._max_chunk_size)
        headers["Mex-Chunk-Range"] = "1:{}".format(len(chunks))
        chunk_iterator = iter(chunks)

        chunk1 = maybe_compressed(six.next(chunk_iterator))
        response1 = requests.post(
            "{}/messageexchange/{}/outbox".format(self._url, self._mailbox),
            data=chunk1,
            headers=headers,
            cert=self._cert,
            verify=self._verify)
        json_resp = response1.json()
        if response1.status_code == 417 or "errorDescription" in json_resp:
            raise MeshError(json_resp["errorDescription"], json_resp)
        message_id = json_resp["messageID"]

        for i, chunk in enumerate(chunk_iterator):
            chunk_num = i + 2
            headers = {
                "Content-Type": "application/octet-stream",
                "Mex-Chunk-Range": "{}:{}".format(chunk_num, len(chunks)),
                "Mex-From": self._mailbox,
                "Authorization": self._token_generator()
            }
            response = requests.post(
                "{}/messageexchange/{}/outbox/{}/{}".format(
                    self._url, self._mailbox, message_id, chunk_num),
                data=maybe_compressed(chunk),
                headers=headers,
                cert=self._cert,
                verify=self._verify)
            response.raise_for_status()

        return message_id

    def acknowledge_message(self, message_id):
        message_id = getattr(message_id, "_msg_id", message_id)
        response = requests.put(
            "{}/messageexchange/{}/inbox/{}/status/acknowledged".format(
                self._url, self._mailbox, message_id),
            headers={
                "Authorization": self._token_generator(),
            },
            cert=self._cert,
            verify=self._verify)
        response.raise_for_status()

    def iterate_all_messages(self):
        for msg_id in self.list_messages():
            yield self.retrieve_message(msg_id)


class _Message(object):
    def __init__(self, msg_id, response, client):
        self._msg_id = msg_id
        self._client = client
        headers = response.headers
        for key, value in _OPTIONAL_HEADERS.items():
            header_value = headers.get(value, None)
            if key in ["compressed", "encrypted"]:
                header_value = header_value or "FALSE"
                header_value = header_value.upper() == "TRUE"
            setattr(self, key, header_value)
        chunk, chunk_count = map(int, headers["Mex-Chunk-Range"].split(":"))
        maybe_decompress = (
            lambda stream: GzipDecompressStream(stream) if headers.get("Content-Encoding") == "gzip" else stream
        )
        self._response = CombineStreams(
            chain([maybe_decompress(response.raw)], (maybe_decompress(
                client.retrieve_message_chunk(msg_id, str(
                    i + 2))) for i in range(chunk_count - 1))))

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
