from __future__ import absolute_import
import codecs
import collections
import uuid
import hmac
import datetime
import os.path
import pkg_resources
import platform
import requests
import six
import time
import warnings
from io import BytesIO
from itertools import chain
from hashlib import sha256
from .io_helpers import \
    CombineStreams, SplitStream, GzipCompressStream, GzipDecompressStream
from .key_helper import get_shared_key_from_environ

MOCK_CA_CERT = pkg_resources.resource_filename('mesh_client', "ca.cert.pem")
MOCK_CERT = pkg_resources.resource_filename('mesh_client', "client.cert.pem")
MOCK_KEY = pkg_resources.resource_filename('mesh_client', "client.key.pem")

MOCK_SSL_OPTS = {
    "verify": MOCK_CA_CERT,
    "cert": (MOCK_CERT, MOCK_KEY)
}
"""
Usable default values for verify and cert, providing certificates and keys
which should work with mock_server. Note that these certs will not work with
any NHS Digital test environments - such certs must be obtained from
NHS Digital.
"""
default_ssl_opts = MOCK_SSL_OPTS

INT_CA_CERT = pkg_resources.resource_filename('mesh_client', "nhs-int-ca-bundle.pem")
DEV_CA_CERT = pkg_resources.resource_filename('mesh_client', "nhs-dev-ca-bundle.pem")
DEP_CA_CERT = pkg_resources.resource_filename('mesh_client', "nhs-dep-ca-bundle.pem")
TRAIN_CA_CERT = pkg_resources.resource_filename('mesh_client', "nhs-train-ca-bundle.pem")
LIVE_CA_CERT = pkg_resources.resource_filename('mesh_client', "nhs-live-root-ca.pem")
OPENTEST_CA_CERT = pkg_resources.resource_filename('mesh_client', "nhs-opt-ca-bundle.pem")
DIGICERT_CA_CERT = pkg_resources.resource_filename('mesh_client', "nhs-digicert-ca-bundle.pem")
IG_INT_CA_CERT = pkg_resources.resource_filename('mesh_client', "nhs-ig-int-ca-bundle.pem")


_OPTIONAL_HEADERS = {
    "workflow_id": "Mex-WorkflowID",
    "filename": "Mex-FileName",
    "local_id": "Mex-LocalID",
    "message_type": "Mex-MessageType",
    "process_id": "Mex-ProcessID",
    "subject": "Mex-Subject",
    "encrypted": "Mex-Content-Encrypted",
    "compressed": "Mex-Content-Compressed",
    "checksum": "Mex-Content-Checksum"
}

_RECEIVE_HEADERS = {
    "sender": "Mex-From",
    "recipient": "Mex-To",
    "message_id": "Mex-MessageID",
    "version": "Mex-Version",
    "partner_id": "Mex-PartnerID",
    "recipient_smtp": "Mex-ToSMTP",
    "sender_smtp": "Mex-FromSMTP",
}
_RECEIVE_HEADERS.update(_OPTIONAL_HEADERS)


VERSION = pkg_resources.get_distribution('mesh_client').version


Endpoint = collections.namedtuple('Endpoint', ['url', 'verify', 'cert'])
LOCAL_MOCK_ENDPOINT = Endpoint('https://localhost:8000', MOCK_CA_CERT, (MOCK_CERT, MOCK_KEY))
LOCAL_FAKE_ENDPOINT = Endpoint('https://localhost:8829', MOCK_CA_CERT, (MOCK_CERT, MOCK_KEY))
NHS_INT_ENDPOINT = Endpoint('https://msg.int.spine2.ncrs.nhs.uk', INT_CA_CERT, None)
NHS_DEV_ENDPOINT = Endpoint('https://msg.dev.spine2.ncrs.nhs.uk', DEV_CA_CERT, None)
NHS_DEP_ENDPOINT = Endpoint('https://msg.dep.spine2.ncrs.nhs.uk', DEP_CA_CERT, None)
NHS_TRAIN_ENDPOINT = Endpoint('https://msg.train.spine2.ncrs.nhs.uk', TRAIN_CA_CERT, None)
NHS_LIVE_ENDPOINT = Endpoint('https://mesh-sync.national.ncrs.nhs.uk', LIVE_CA_CERT, None)
NHS_OPENTEST_ENDPOINT = Endpoint('https://192.168.128.11', OPENTEST_CA_CERT, None)
NHS_INTERNET_GATEWAY_ENDPOINT = Endpoint('https://mesh.spineservices.nhs.uk', DIGICERT_CA_CERT, None)
NHS_INTERNET_GATEWAY_INT_ENDPOINT = Endpoint('https://msg.intspineservices.nhs.uk', IG_INT_CA_CERT, None)


class MeshError(Exception):
    pass


class MeshClient(object):
    """
    A class representing a single MESH session, for a given user on a given
    endpoint. This class handles details such as chunking and compression
    transparently.
    """

    def __init__(self,
                 url,
                 mailbox,
                 password,
                 shared_key=get_shared_key_from_environ(),
                 cert=None,
                 verify=None,
                 max_chunk_size=75 * 1024 * 1024,
                 proxies=None,
                 transparent_compress=False,
                 max_chunk_retries=0,
                 timeout=10*60):
        """
        Create a new MeshClient.

        At a minimum, you must provide an endpoint url, a mailbox and a
        password. The endpoint URL can either be a string, or a preconfigured
        endpoint. Currently the following endpoints are preconfigured:

        LOCAL_MOCK_ENDPOINT
        LOCAL_FAKE_ENDPOINT
        NHS_INT_ENDPOINT
        NHS_LIVE_ENDPOINT
        NHS_OPENTEST_ENDPOINT
        NHS_INTERNET_ENDPOINT

        Since MESH uses mutual authentication, it is also highly
        advisable to provide SSL information, in the form of cert and verify.
        these take the same format as in the requests library, so you would
        typically provide a filename for a CA cert as verify, and a tuple
        containing two filenames (a client cert and a private key) for cert.

        If you have chosen to use a preconfigured endpoint, then you a sane
        default value will be used for the CA cert, so you should not have to
        configure verify. For mock and fake endpoints, default values for cert
        are provided, so you will not need to configure that either.

        You can also optionally specify the maximum file size before chunking,
        and whether messages should be compressed, transparently, before
        sending.
        """
        self._session = requests.Session()
        self._session.headers = {
            "mex-ClientVersion": "mesh_client=={}".format(VERSION),
            "mex-OSArchitecture": platform.processor(),
            "mex-OSName": platform.system(),
            "mex-OSVersion": "{} {}".format(platform.release(), platform.version()),
            "mex-JavaVersion": "N/A",
            "Accept-Encoding": "gzip"
        }
        self._session.auth = AuthTokenGenerator(shared_key, mailbox, password)
        if hasattr(url, 'url'):
            self._url = url.url
        else:
            self._url = url

        if hasattr(url, 'cert') and cert is None:
            self._session.cert = url.cert
        else:
            self._session.cert = cert

        if hasattr(url, 'verify') and verify is None:
            self._session.verify = url.verify
        else:
            self._session.verify = verify

        self._session.proxies = proxies or {}
        self._mailbox = mailbox
        self._max_chunk_size = max_chunk_size
        self._transparent_compress = transparent_compress
        self._max_chunk_retries = max_chunk_retries
        self._timeout = timeout
        self._close_called = False

    def handshake(self):
        """
        List all messages in user's inbox. Returns a list of message_ids
        """
        response = self._session.post(
            "{}/messageexchange/{}".format(self._url, self._mailbox),
            timeout=self._timeout
        )

        response.raise_for_status()

        return b'hello'

    def count_messages(self):
        """
        Count all messages in user's inbox. Returns an integer
        """
        response = self._session.get(
            "{}/messageexchange/{}/count".format(self._url, self._mailbox),
            timeout=self._timeout)
        response.raise_for_status()
        return response.json()["count"]

    def get_tracking_info(self, tracking_id):
        """
        Gets tracking information from MESH about a message, by its local message id.
        Returns a dictionary, in much the same format that MESH provides it.
        """
        response = self._session.get(
            "{}/messageexchange/{}/outbox/tracking/{}".format(self._url, self._mailbox, tracking_id),
            timeout=self._timeout)
        response.raise_for_status()
        return response.json()

    def lookup_endpoint(self, organisation_code, workflow_id):
        """
        Lookup a mailbox by organisation code and workflow id.
        Returns a dictionary, in much the same format that MESH provides it.
        """
        response = self._session.get(
            "{}/endpointlookup/mesh/{}/{}".format(self._url, organisation_code, workflow_id),
            timeout=self._timeout)
        response.raise_for_status()
        return response.json()

    def list_messages(self):
        """
        List all messages in user's inbox. Returns a list of message_ids
        """
        response = self._session.get(
            "{}/messageexchange/{}/inbox".format(self._url, self._mailbox),
            timeout=self._timeout)
        response.raise_for_status()
        return response.json()["messages"]

    def retrieve_message(self, message_id):
        """
        Retrieve a message based on its message_id. This will return a Message
        object
        """
        message_id = getattr(message_id, "_msg_id", message_id)
        response = self._session.get(
            "{}/messageexchange/{}/inbox/{}".format(self._url, self._mailbox, message_id),
            stream=True,
            timeout=self._timeout)
        response.raise_for_status()
        return Message(message_id, response, self)

    def retrieve_message_chunk(self, message_id, chunk_num):
        response = self._session.get(
            "{}/messageexchange/{}/inbox/{}/{}".format(self._url, self._mailbox, message_id, chunk_num),
            stream=True,
            timeout=self._timeout)
        response.raise_for_status()
        return response

    def send_message(self,
                     recipient,
                     data,
                     **kwargs):
        """
        Send a message to recipient containing data.

        This method optionally allows the user to provide the following keyword
        arguments, which specify properties of the message, and map to
        the equivalent properties in MESH - either headers or control file
        entries, depending on the type of consumer:

        workflow_id
        filename
        local_id
        message_type
        process_id
        subject
        encrypted
        compressed
        checksum
        sender
        recipient
        message_id
        version
        partner_id
        recipient_smtp
        sender_smtp

        Note that compressed refers to *non-transparent* compression - the
        client will not attempt to compress or decompress data. Transparent
        compression for sending is enabled as a constructor option.
        """
        transparent_compress = self._transparent_compress
        maybe_compressed = (
            lambda stream: GzipCompressStream(
                stream) if transparent_compress else stream
        )
        headers = {
            "Mex-From": self._mailbox,
            "Mex-To": recipient,
            "Mex-MessageType": 'DATA',
            "Mex-Version": '1.0'
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
        response1 = self._session.post(
            "{}/messageexchange/{}/outbox".format(self._url, self._mailbox),
            data=chunk1,
            headers=headers,
            timeout=self._timeout)
        json_resp = response1.json()
        if response1.status_code == 417 or "errorDescription" in json_resp:
            raise MeshError(json_resp["errorDescription"], json_resp)
        message_id = json_resp["messageID"]

        for i, chunk in enumerate(chunk_iterator):
            data = maybe_compressed(chunk)

            if self._max_chunk_retries > 0:
                if hasattr(data, 'read'):
                    data = data.read()
                buf = BytesIO(data)
            else:
                buf = data

            chunk_num = i + 2
            headers = {
                "Content-Type": "application/octet-stream",
                "Mex-Chunk-Range": "{}:{}".format(chunk_num, len(chunks)),
                "Mex-From": self._mailbox,
            }
            if transparent_compress:
                headers["Mex-Content-Compress"] = "TRUE"
                headers["Content-Encoding"] = "gzip"

            response = None
            for i in range(self._max_chunk_retries + 1):
                if self._max_chunk_retries > 0:
                    buf.seek(0)

                # non-linear delay in terms of squares
                time.sleep(i**2)

                response = self._session.post(
                    "{}/messageexchange/{}/outbox/{}/{}".format(
                        self._url, self._mailbox, message_id, chunk_num),
                    data=buf,
                    headers=headers,
                    timeout=self._timeout)

                # check other successful response codes
                if response.status_code == 200 or response.status_code == 202:
                    break
            else:
                response.raise_for_status()

        return message_id

    def acknowledge_message(self, message_id):
        """
        Acknowledge a message_id, deleting it from MESH.
        """
        message_id = getattr(message_id, "_msg_id", message_id)
        response = self._session.put(
            "{}/messageexchange/{}/inbox/{}/status/acknowledged".format(
                self._url, self._mailbox, message_id),
            timeout=self._timeout)
        response.raise_for_status()

    def iterate_all_messages(self):
        """
        Iterate over a list of Message objects for all messages in the user's
        inbox. This is provided as a convenience function, but will be
        slower than list_messages if only the message_ids are needed, since it
        will also begin to download messages.
        """
        for msg_id in self.list_messages():
            yield self.retrieve_message(msg_id)

    def close(self):
        self._close_called = True
        self._session.close()

    def __del__(self):
        if not self._close_called:
            warnings.warn(
                "The API of MeshClient changed in mesh_client 1.0. Each"
                " MeshClient instance must now be closed when the instance is"
                " no longer needed. This can be achieved by using the close"
                " method, or by using MeshClient in a with block. The"
                " connection pool will be closed for you by the destructor"
                " on this occasion, but you should not rely on this."
            )
            self.close()

    def __enter__(self):
        return self

    def __exit__(self, type_, value, tb):
        self.close()


class Message(object):
    """
    An object representing a message received from MESH. This is a file-like
    object, and can be passed to anything that expects an object with a `read`
    method.

    Any properties set on the message (as headers in MESH API, or control file
    entries) are available as attributes of this object. The following are
    supported:

    workflow_id
    filename
    local_id
    message_type
    process_id
    subject
    encrypted
    compressed

    Note that compressed refers to *non-transparent* compression - the
    client will not attempt to compress or decompress data. Transparent
    compression is handled automatically, with no intervention needed.

    Messages have a read method, and will handle chunking and transparent
    compression automatically. Once the data has been read, you must close the
    underlying stream using the close method. Data can only be read once. If
    you need to read it again, retrieve the message again.

    Messages can be used as context managers. When used in this way, streams
    will be closed automatically, and messages will be acknowledged if
    no exceptions are thrown whilst handling the message.
    """

    def __init__(self, msg_id, response, client):
        self._msg_id = msg_id
        self._client = client
        self._mex_headers = {}

        headers = response.headers
        for key, value in six.iteritems(headers):
            lkey = key.lower()
            if lkey.startswith('mex-'):
                self._mex_headers[lkey[4:]] = value

        for key, value in _RECEIVE_HEADERS.items():
            header_value = headers.get(value, None)
            if key in ["compressed", "encrypted"]:
                header_value = header_value or "FALSE"
                header_value = header_value.upper() == "TRUE"
            setattr(self, key, header_value)
        chunk, chunk_count = map(
            int, headers.get("Mex-Chunk-Range", "1:1").split(":"))
        maybe_decompress = (
            lambda resp:
            GzipDecompressStream(resp.raw)
            if resp.headers.get("Content-Encoding") == "gzip" else resp.raw
        )
        self._response = CombineStreams(
            chain([maybe_decompress(response)], (maybe_decompress(
                client.retrieve_message_chunk(msg_id, str(
                    i + 2))) for i in range(chunk_count - 1))))

    def id(self):
        """return the message id

        Returns:
            str: message id
        """
        return self._msg_id

    def read(self, n=None):
        """
        Read up to n bytes from the message, or read the remainder of the
        message, if n is not provided.
        """
        return self._response.read(n)

    def readline(self):
        """
        Read a single line from the message
        """
        return self._response.readline()

    def readlines(self):
        """
        Read all lines from the message
        """
        return self._response.readlines()

    def close(self):
        """Close the stream underlying this message"""
        if hasattr(self._response, "close"):
            try:
                self._response.close()
            finally:
                self._response = None

    def acknowledge(self):
        """
        Acknowledge this message, and delete it from MESH
        """
        self._client.acknowledge_message(self._msg_id)

    def mex_header(self, key, default=None):
        """ get a mex header if present

        Args:
            key (str): key
            default (any): default value
        Returns:
            str: the mex header value
        """
        return self._mex_headers.get(key, default)

    def mex_headers(self):
        """returns a generator iteritems for all the headers"""
        return six.iteritems(self._mex_headers)

    def __enter__(self):
        return self

    def __exit__(self, typ, value, traceback):
        try:
            if not value:
                self.acknowledge()
        finally:
            self.close()

    def __iter__(self):
        """
        Iterate through lines of the message
        """
        return iter(self._response)


class AuthTokenGenerator(object):

    def __init__(self, key, mailbox, password):
        self._key = key
        self._mailbox = mailbox
        self._password = password
        self._nonce = uuid.uuid4()
        self._nonce_count = 0

    def __call__(self, r=None):
        token = self.generate_token()
        if r is not None:
            # This is being used as a Requests auth handler
            r.headers['Authorization'] = token
            return r
        else:
            # This is being used in its legacy capacity
            return token

    def generate_token(self):
        now = datetime.datetime.now().strftime("%Y%m%d%H%M")
        public_auth_data = _combine(self._mailbox, self._nonce,
                                    self._nonce_count, now)
        private_auth_data = _combine(self._mailbox, self._nonce,
                                     self._nonce_count, self._password, now)
        myhash = hmac.HMAC(self._key, private_auth_data.encode("ASCII"),
                           sha256).hexdigest()
        self._nonce_count += 1
        return "NHSMESH {public_auth_data}:{myhash}".format(**locals())


# Preserve old name, even though it's part of the API now
_AuthTokenGenerator = AuthTokenGenerator


def _combine(*elements):
    return ":".join(str(x) for x in elements)
