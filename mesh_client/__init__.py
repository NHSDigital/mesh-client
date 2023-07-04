import collections
import datetime
import functools
import hmac
import os.path
import platform
import ssl
import sys
import time
import uuid
import warnings
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from itertools import chain
from typing import Any, Dict, List, Optional, Tuple, TypeVar, Union, cast
from urllib.parse import quote as q

import requests
from requests.adapters import HTTPAdapter

from .io_helpers import (
    CombineStreams,
    GzipCompressStream,
    GzipDecompressStream,
    SplitStream,
)
from .key_helper import get_shared_key_from_environ
from .types import (
    EndpointLookupResponse_v1,
    ListMessageResponse_v1,
    SendMessageErrorResponse_v1,
    SendMessageResponse_v1,
    TrackingResponse_v1,
)

if sys.version_info[:2] >= (3, 8):
    # TODO: Import directly (no need for conditional) when `python_requires = >= 3.8`
    from importlib.metadata import PackageNotFoundError, version
else:
    from importlib_metadata import PackageNotFoundError, version


def _get_version(*names: str) -> str:
    """ """
    for name in names:
        try:
            pkg_version = version(name)
            return pkg_version
        except PackageNotFoundError:
            continue
    return "unknown"


__version__ = _get_version("mesh-client")

_PACKAGE_DIR = os.path.dirname(__file__)

INT_CA_CERT = os.path.join(_PACKAGE_DIR, "nhs-int-ca-bundle.pem")
DEV_CA_CERT = os.path.join(_PACKAGE_DIR, "nhs-dev-ca-bundle.pem")
DEP_CA_CERT = os.path.join(_PACKAGE_DIR, "nhs-dep-ca-bundle.pem")
TRAIN_CA_CERT = os.path.join(_PACKAGE_DIR, "nhs-train-ca-bundle.pem")
LIVE_CA_CERT = os.path.join(_PACKAGE_DIR, "nhs-live-root-ca.pem")
OPENTEST_CA_CERT = os.path.join(_PACKAGE_DIR, "nhs-opt-ca-bundle.pem")
DIGICERT_CA_CERT = os.path.join(_PACKAGE_DIR, "nhs-digicert-ca-bundle.pem")
IG_INT_CA_CERT = os.path.join(_PACKAGE_DIR, "nhs-ig-int-ca-bundle.pem")
IG_LIVE_CA_CERT = os.path.join(_PACKAGE_DIR, "nhs-ig-live-ca-bundle.pem")


_OPTIONAL_HEADERS = {
    "workflow_id": "Mex-WorkflowID",
    "filename": "Mex-FileName",
    "local_id": "Mex-LocalID",
    "message_type": "Mex-MessageType",
    "subject": "Mex-Subject",
    "encrypted": "Mex-Content-Encrypted",
    "compressed": "Mex-Content-Compressed",
    "checksum": "Mex-Content-Checksum",
    "content_type": "Content-Type",
}

_BOOLEAN_HEADERS = {"compressed", "encrypted"}

_RECEIVE_HEADERS = {
    "sender": "Mex-From",
    "recipient": "Mex-To",
    "message_id": "Mex-MessageID",
    "version": "Mex-Version",
    "partner_id": "Mex-PartnerID",
}
_RECEIVE_HEADERS.update(_OPTIONAL_HEADERS)


Endpoint = collections.namedtuple("Endpoint", ["url", "verify", "cert", "check_hostname"])

NHS_INT_ENDPOINT = Endpoint("https://msg.int.spine2.ncrs.nhs.uk", INT_CA_CERT, None, False)
NHS_DEV_ENDPOINT = Endpoint("https://msg.dev.spine2.ncrs.nhs.uk", DEV_CA_CERT, None, False)
NHS_DEP_ENDPOINT = Endpoint("https://msg.dep.spine2.ncrs.nhs.uk", DEP_CA_CERT, None, False)
NHS_TRAIN_ENDPOINT = Endpoint("https://msg.train.spine2.ncrs.nhs.uk", TRAIN_CA_CERT, None, False)
NHS_LIVE_ENDPOINT = Endpoint("https://mesh-sync.national.ncrs.nhs.uk", LIVE_CA_CERT, None, False)
NHS_OPENTEST_ENDPOINT = Endpoint("https://192.168.128.11", OPENTEST_CA_CERT, None, False)
NHS_INTERNET_GATEWAY_ENDPOINT = Endpoint("https://mesh-sync.spineservices.nhs.uk", IG_LIVE_CA_CERT, None, True)
NHS_INTERNET_GATEWAY_INT_ENDPOINT = Endpoint("https://msg.intspineservices.nhs.uk", IG_INT_CA_CERT, None, True)


def deprecated(reason=None):
    """This is a decorator which can be used to mark functions
    as deprecated. It will result in a warning being emitted
    when the function is used."""

    def decorator(func):
        @functools.wraps(func)
        def new_func(*args, **kwargs):
            msg_extra = (reason or "").strip()
            if msg_extra:
                msg_extra = " " + msg_extra
            message = f"Call to deprecated function {func.__name__} {msg_extra}."
            warnings.warn(message, category=DeprecationWarning, stacklevel=2)
            return func(*args, **kwargs)

        return new_func

    return decorator


class MeshError(Exception):
    pass


class SSLContextAdapter(HTTPAdapter):
    def __init__(
        self,
        url: Union[str, Endpoint],
        cert: Optional[Union[Tuple[str], Tuple[str, str], Tuple[str, str, str]]] = None,
        verify: Optional[Union[str, bool]] = None,
        check_hostname: Optional[bool] = None,
    ):
        self.url = url
        self.cert = cert
        self.verify = verify
        self.check_hostname = check_hostname
        if check_hostname is None and hasattr(url, "check_hostname"):
            self.check_hostname = url.check_hostname

        if cert is None and hasattr(url, "cert"):
            self.cert = url.cert

        if verify is None and hasattr(url, "verify"):
            self.verify = url.verify

        super().__init__()

    def init_poolmanager(self, *args, **kwargs):
        context = ssl.create_default_context()

        if self.cert and isinstance(self.cert, (tuple, list)):
            context.load_cert_chain(*self.cert)

        if self.verify:
            if isinstance(self.verify, (str, bytes)):
                context.load_verify_locations(self.verify)

            if context.check_hostname is not None:
                context.check_hostname = cast(bool, self.check_hostname)

            context.verify_mode = ssl.CERT_REQUIRED
            if self.check_hostname is not False:
                context.hostname_checks_common_name = True

        if self.verify is False:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE

        kwargs["ssl_context"] = context
        return super(SSLContextAdapter, self).init_poolmanager(*args, **kwargs)


class MeshClient(object):
    """
    A class representing a single MESH session, for a given user on a given
    endpoint. This class handles details such as chunking and compression
    transparently.
    """

    def __init__(
        self,
        url: Union[str, Endpoint],
        mailbox: str,
        password: str,
        shared_key: Optional[bytes] = None,
        cert: Optional[Union[Tuple[str], Tuple[str, str], Tuple[str, str, str]]] = None,
        verify: Optional[Union[str, bool]] = None,
        check_hostname: Optional[bool] = None,
        max_chunk_size=75 * 1024 * 1024,
        proxies: Optional[Dict[str, str]] = None,
        transparent_compress: bool = False,
        max_chunk_retries: int = 0,
        timeout: Union[int, float] = 10 * 60,
    ):
        """
        Create a new MeshClient.

        At a minimum, you must provide an endpoint url, a mailbox and a
        password. The endpoint URL can either be a string, or a preconfigured
        endpoint. Currently the following endpoints are preconfigured:

        NHS_INT_ENDPOINT
        NHS_LIVE_ENDPOINT
        NHS_OPENTEST_ENDPOINT
        NHS_INTERNET_GATEWAY_INT_ENDPOINT
        NHS_INTERNET_GATEWAY_ENDPOINT

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

        shared_key = shared_key or get_shared_key_from_environ()

        self._session = requests.Session()
        adapter = SSLContextAdapter(url, cert, verify, check_hostname)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)
        self._session.headers = {
            "User-Agent": (
                f"mesh_client;{__version__};N/A;{platform.processor() or platform.machine()};"
                f"{platform.system()};{platform.release()} {platform.version()}"
            ),
            "Accept-Encoding": "gzip",
        }
        self._session.auth = AuthTokenGenerator(shared_key, mailbox, password)
        if hasattr(url, "url"):
            self._url = url.url
        else:
            self._url = url

        if verify is not None:
            self._session.verify = verify
        elif hasattr(url, "verify"):
            self._session.verify = url.verify

        self._session.proxies = proxies or {}
        self._mailbox = mailbox
        self._max_chunk_size = max_chunk_size
        self._transparent_compress = transparent_compress
        self._max_chunk_retries = max_chunk_retries
        self._timeout = timeout
        self._close_called = False

    @property
    def mailbox_url(self) -> str:
        return f"{self._url}/messageexchange/{q(self._mailbox)}"

    def ping(self) -> dict:
        """
        just connect to the _ping endpoint
        """
        response = self._session.get(f"{self._url}/messageexchange/_ping", timeout=self._timeout)

        response.raise_for_status()

        return cast(dict, response.json())

    def handshake(self):
        """
        List all messages in user's inbox. Returns a list of message_ids
        """
        headers = {
            "mex-ClientVersion": f"mesh_client=={__version__}",
            "mex-OSArchitecture": platform.processor() or platform.machine(),
            "mex-OSName": platform.system(),
            "mex-OSVersion": f"{platform.release()} {platform.version()}",
            "mex-JavaVersion": "N/A",
        }
        response = self._session.post(self.mailbox_url, headers=headers, timeout=self._timeout)

        response.raise_for_status()

        return b"hello"

    @deprecated("this api endpoint is marked as deprecated")
    def count_messages(self) -> int:
        """
        Count all messages in user's inbox. Returns an integer
        """
        response = self._session.get(f"{self.mailbox_url}/count", timeout=self._timeout)
        response.raise_for_status()
        return cast(int, response.json()["count"])

    def track_by_message_id(self, message_id: str) -> TrackingResponse_v1:
        """
        Gets tracking information from MESH about a message, by its  message id.
        Returns a dictionary, in much the same format that MESH provides it.
        """
        url = f"{self.mailbox_url}/outbox/tracking?messageID={q(message_id)}"

        response = self._session.get(url, timeout=self._timeout)
        response.raise_for_status()
        return cast(TrackingResponse_v1, response.json())

    def _get_tracking_url(self, local_id: Optional[str] = None, message_id: Optional[str] = None) -> str:
        if message_id:
            return f"{self.mailbox_url}/outbox/tracking?messageID={q(message_id)}"

        if local_id:
            return f"{self.mailbox_url}/outbox/tracking/{q(local_id)}"

        raise ValueError(
            "Exactly one of local message id (called tracking_id, for historical reasons) "
            "and message_id must be provided"
        )

    @deprecated(reason="tracking by local_id is deprecated, please use 'track_by_message_id'")
    def get_tracking_info(
        self, local_id: Optional[str] = None, message_id: Optional[str] = None
    ) -> TrackingResponse_v1:
        """
        Gets tracking information from MESH about a message, by its local message id.
        Returns a dictionary, in much the same format that MESH provides it.
        """

        url = self._get_tracking_url(local_id, message_id)

        response = self._session.get(url, timeout=self._timeout)
        response.raise_for_status()
        return cast(TrackingResponse_v1, response.json())

    def lookup_endpoint(self, ods_code: str, workflow_id: str) -> EndpointLookupResponse_v1:
        """
        Lookup a mailbox by organisation code and workflow id.
        Returns a dictionary, in much the same format that MESH provides it.
        """
        response = self._session.get(
            f"{self._url}/messageexchange/endpointlookup/{q(ods_code)}/{q(workflow_id)}",
            timeout=self._timeout,
        )
        response.raise_for_status()
        return cast(EndpointLookupResponse_v1, response.json())

    def list_messages(self) -> List[str]:
        """
        List all messages in user's inbox. Returns a list of message_ids
        """
        response = self._session.get(f"{self.mailbox_url}/inbox", timeout=self._timeout)
        response.raise_for_status()
        return cast(ListMessageResponse_v1, response.json())["messages"]

    def retrieve_message(self, message_id: str):
        """
        Retrieve a message based on its message_id. This will return a Message
        object
        """
        message_id = getattr(message_id, "_msg_id", message_id)
        response = self._session.get(
            f"{self.mailbox_url}/inbox/{q(message_id)}",
            stream=True,
            timeout=self._timeout,
        )
        response.raise_for_status()
        return Message(message_id, response, self)

    def retrieve_message_chunk(self, message_id: str, chunk_num: Union[int, str]):
        response = self._session.get(
            f"{self.mailbox_url}/inbox/{q(message_id)}/{chunk_num}",
            stream=True,
            timeout=self._timeout,
        )
        response.raise_for_status()
        return response

    def send_message(
        self,
        recipient: str,
        data,
        max_chunk_size: Optional[int] = None,
        **kwargs,
    ) -> str:
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
        subject
        encrypted
        compressed
        checksum
        sender
        recipient
        message_id
        version
        partner_id

        Note that compressed refers to *non-transparent* compression - the
        client will not attempt to compress or decompress data. Transparent
        compression for sending is enabled as a constructor option.
        """
        transparent_compress = self._transparent_compress

        def maybe_compressed(maybe_compress: bytes):
            if not transparent_compress:
                return maybe_compress
            return GzipCompressStream(maybe_compress)

        headers = {
            "Mex-From": self._mailbox,
            "Mex-To": recipient,
            "Mex-MessageType": "DATA",
            "Mex-Version": "1.0",
            "Content-Type": "application/octet-stream",
        }

        for key, value in kwargs.items():
            if key in _OPTIONAL_HEADERS:
                if key in _BOOLEAN_HEADERS:
                    value = "Y" if value else "N"
                headers[_OPTIONAL_HEADERS[key]] = str(value)
            else:
                optional_args = ", ".join(["recipient", "data"] + list(_OPTIONAL_HEADERS.keys()))
                raise TypeError(f"Unrecognised keyword argument '{key}'.  optional arguments are: {optional_args}")

        if transparent_compress:
            headers["Mex-Content-Compress"] = "Y"
            headers["Content-Encoding"] = "gzip"

        max_chunk_size = max_chunk_size or self._max_chunk_size
        chunks = SplitStream(data, max_chunk_size)
        headers["Mex-Chunk-Range"] = f"1:{len(chunks)}"
        chunk_iterator = iter(chunks)

        chunk1 = maybe_compressed(next(chunk_iterator))
        response1 = self._session.post(
            f"{self.mailbox_url}/outbox",
            data=chunk1,
            headers=headers,
            timeout=self._timeout,
        )
        # MESH server dumps XML SOAP output on internal server error
        if response1.status_code >= 500:
            response1.raise_for_status()

        response_dict = response1.json()
        if response1.status_code == 417 or "errorDescription" in response_dict:
            error_response = cast(SendMessageErrorResponse_v1, response_dict)
            raise MeshError(error_response["errorDescription"], error_response)

        if response1.status_code not in (200, 202):
            raise MeshError(response_dict)

        success_response = cast(SendMessageResponse_v1, response_dict)

        message_id = success_response["messageID"]

        for i, chunk in enumerate(chunk_iterator):
            data = maybe_compressed(chunk)

            if self._max_chunk_retries > 0:
                if hasattr(data, "read"):
                    data = data.read()
                buf = BytesIO(data)
            else:
                buf = data

            chunk_num = i + 2
            headers = {
                "Content-Type": "application/octet-stream",
                "Mex-Chunk-Range": f"{chunk_num}:{len(chunks)}",
                "Mex-From": self._mailbox,
            }
            if transparent_compress:
                headers["Mex-Content-Compress"] = "Y"
                headers["Content-Encoding"] = "gzip"

            for i in range(self._max_chunk_retries + 1):
                if self._max_chunk_retries > 0:
                    buf.seek(0)

                # non-linear delay in terms of squares
                time.sleep(i**2)

                response = self._session.post(
                    f"{self.mailbox_url}/outbox/{q(message_id)}/{chunk_num}",
                    data=buf,
                    headers=headers,
                    timeout=self._timeout,
                )

                # check other successful response codes
                if response.status_code in (200, 202):
                    break

                if i < self._max_chunk_retries:
                    continue

                response.raise_for_status()

        return message_id

    def acknowledge_message(self, message_id: str):
        """
        Acknowledge a message_id, deleting it from MESH.
        """
        message_id = getattr(message_id, "_msg_id", message_id)
        response = self._session.put(
            f"{self.mailbox_url}/inbox/{q(message_id)}/status/acknowledged",
            timeout=self._timeout,
        )
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


@dataclass
class _MessageAttrs:
    """
    this is for type hinting on the commonly used message attrs below ( which are dynamically generated )
    """

    message_id: str
    message_type: str
    recipient: str
    content_type: str
    sender: Optional[str] = None

    workflow_id: Optional[str] = None
    filename: Optional[str] = None
    local_id: Optional[str] = None
    partner_id: Optional[str] = None
    chunk_range: Optional[str] = None

    subject: Optional[str] = None
    encrypted: Optional[Union[str, bool]] = None
    compressed: Optional[Union[str, bool]] = None


TDefault = TypeVar("TDefault")


class _BaseMessage:
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
    subject
    encrypted
    compressed
    checksum
    content_type

    Note that compressed refers to *non-transparent* compression - the
    client will not attempt to compress or decompress data. Transparent (Content-Encoding)
    compression is handled automatically, with no intervention needed.
    This is merely a header that is passed through to let the recipient know the decoded content is further compressed.


    Messages have a read method, and will handle chunking and transparent
    compression automatically. Once the data has been read, you must close the
    underlying stream using the close method. Data can only be read once. If
    you need to read it again, retrieve the message again.

    Messages can be used as context managers. When used in this way, streams
    will be closed automatically, and messages will be acknowledged if
    no exceptions are thrown whilst handling the message.
    """

    def __init__(self, msg_id: str, response, client):
        self._msg_id = msg_id
        self._client = client
        self._mex_headers: Dict[str, Any] = {}

        headers = response.headers
        for header, header_value in headers.items():
            lkey = header.lower()
            if lkey.startswith("mex-"):
                self._mex_headers[lkey[4:]] = header_value

        for attribute, header in _RECEIVE_HEADERS.items():
            header_value = headers.get(header, None)
            if attribute in _BOOLEAN_HEADERS:
                header_value = header_value or "N"
                header_value = header_value.upper() in ["Y", "TRUE"]
            setattr(self, attribute, header_value)
        chunk, chunk_count = map(int, headers.get("Mex-Chunk-Range", "1:1").split(":"))
        maybe_decompress = (
            lambda resp: GzipDecompressStream(resp.raw) if resp.headers.get("Content-Encoding") == "gzip" else resp.raw
        )
        self._response = CombineStreams(
            chain(
                [maybe_decompress(response)],
                (maybe_decompress(client.retrieve_message_chunk(msg_id, str(i + 2))) for i in range(chunk_count - 1)),
            )
        )

    def id(self) -> str:
        """return the message id

        Returns:
            str: message id
        """
        return self._msg_id

    def read(self, n=None) -> bytes:
        """
        Read up to n bytes from the message, or read the remainder of the
        message, if n is not provided.
        """
        return self._response.read(n)

    def readline(self) -> bytes:
        """
        Read a single line from the message
        """
        return self._response.readline()

    def readlines(self) -> List[bytes]:
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
                self._response = None  # type: ignore[assignment]

    def acknowledge(self):
        """
        Acknowledge this message, and delete it from MESH
        """
        self._client.acknowledge_message(self._msg_id)

    def mex_header(self, key: str, default: Optional[TDefault] = None) -> Union[str, TDefault]:
        """get a mex header if present

        Args:
            key (str): key
            default (any): default value
        Returns:
            str: the mex header value
        """
        return self._mex_headers.get(key, default)

    def mex_headers(self):
        """returns a generator iteritems for all the headers"""
        return self._mex_headers.items()

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


class Message(_BaseMessage, _MessageAttrs):
    def __init__(self, msg_id: str, response, client):
        super().__init__(msg_id, response, client)


class AuthTokenGenerator(object):
    def __init__(self, key: bytes, mailbox: str, password: str):
        self._key = key
        self._mailbox = mailbox
        self._password = password
        self._nonce = uuid.uuid4()
        self._nonce_count = 0

    def __call__(self, r=None):
        token = self.generate_token()
        if r is not None:
            # This is being used as a Requests auth handler
            r.headers["Authorization"] = token
            return r
        else:
            # This is being used in its legacy capacity
            return token

    def generate_token(self) -> str:
        now = datetime.datetime.utcnow().strftime("%Y%m%d%H%M")
        public_auth_data = f"{self._mailbox}:{self._nonce}:{self._nonce_count}:{now}"
        private_auth_data = f"{self._mailbox}:{self._nonce}:{self._nonce_count}:{self._password}:{now}"
        myhash = hmac.HMAC(self._key, private_auth_data.encode("ASCII"), sha256).hexdigest()
        self._nonce_count += 1
        return f"NHSMESH {public_auth_data}:{myhash}"


# Preserve old name, even though it's part of the API now
_AuthTokenGenerator = AuthTokenGenerator
