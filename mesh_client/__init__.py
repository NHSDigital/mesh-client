import collections
import contextlib
import datetime
import functools
import hmac
import os.path
import platform
import socket  # noqa: F401
import ssl
import sys
import uuid
import warnings
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from itertools import chain
from types import TracebackType
from typing import Any, Dict, Generator, List, Optional, Tuple, TypeVar, Union, cast
from urllib.parse import quote as q
from urllib.parse import urlparse

import requests
from requests import Response
from requests.adapters import HTTPAdapter
from urllib3 import BaseHTTPResponse
from urllib3.connectionpool import ConnectionPool
from urllib3.exceptions import (
    ResponseError,
)
from urllib3.util import create_urllib3_context
from urllib3.util.retry import Retry
from urllib3.util.util import reraise

from .io_helpers import (
    CombineStreams,
    GzipCompressStream,
    GzipDecompressStream,
    SplitStream,
)
from .key_helper import get_shared_key_from_environ
from .types import (
    EndpointLookupResponse_v2,
    ListMessageResponse_v2,
    SendMessageErrorResponse_v1,
    SendMessageErrorResponse_v2,
    SendMessageResponse_v2,
    TrackingResponse_v2,
)

if sys.version_info[:2] < (3, 8):
    warnings.warn("python 3.7 is now end of life", category=DeprecationWarning, stacklevel=2)

if sys.version_info[:2] >= (3, 8):
    # TODO: Import directly (no need for conditional) when `python_requires = >= 3.8`
    from importlib.metadata import PackageNotFoundError, version
else:
    from importlib_metadata import PackageNotFoundError, version


def _get_version(*names: str) -> str:
    """ """
    for name in names:
        with contextlib.suppress(PackageNotFoundError):
            pkg_version = version(name)
            return pkg_version
    return "unknown"


__version__ = _get_version("mesh-client")

_PACKAGE_DIR = os.path.dirname(__file__)

INT_CA_CERT = os.path.join(_PACKAGE_DIR, "nhs-int-ca-bundle.pem")
DEP_CA_CERT = os.path.join(_PACKAGE_DIR, "nhs-dep-ca-bundle.pem")
LIVE_CA_CERT = os.path.join(_PACKAGE_DIR, "nhs-live-ca-bundle.pem")


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


Endpoint = collections.namedtuple(
    "Endpoint", ["url", "verify", "cert", "check_hostname", "hostname_checks_common_name"]
)

DEPRECATED_HSCN_DEP_ENDPOINT = Endpoint("https://msg.dep.spine2.ncrs.nhs.uk", DEP_CA_CERT, None, True, True)
DEPRECATED_HSCN_INT_ENDPOINT = Endpoint("https://msg.int.spine2.ncrs.nhs.uk", INT_CA_CERT, None, True, True)
DEPRECATED_HSCN_LIVE_ENDPOINT = Endpoint("https://mesh-sync.national.ncrs.nhs.uk", LIVE_CA_CERT, None, True, True)
DEP_ENDPOINT = Endpoint("https://msg.depspineservices.nhs.uk", DEP_CA_CERT, None, True, False)
INT_ENDPOINT = Endpoint("https://msg.intspineservices.nhs.uk", INT_CA_CERT, None, True, False)
LIVE_ENDPOINT = Endpoint("https://mesh-sync.spineservices.nhs.uk", LIVE_CA_CERT, None, True, True)

ENDPOINTS = [(name, endpoint) for name, endpoint in locals().items() if name.endswith("_ENDPOINT")]


_HOSTNAME_ENDPOINT_MAP = {urlparse(ep.url).hostname: ep for name, ep in ENDPOINTS}


def try_get_endpoint_from_url(url: str) -> Optional[Endpoint]:
    url_parsed = urlparse(url)
    if not url_parsed.hostname:
        return None
    defaults = _HOSTNAME_ENDPOINT_MAP.get(url_parsed.hostname.lower())
    if not defaults:
        return None

    return Endpoint(url, *defaults[1:])


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


def _looks_like_send_error(status_code: int, response_dict: dict) -> bool:
    if status_code == 417:
        return True
    if "errorDescription" in response_dict:
        return True

    if "detail" in response_dict:
        return True

    return False


def _get_send_error_message(
    response_dict: dict,
) -> Tuple[str, Union[SendMessageErrorResponse_v1, SendMessageErrorResponse_v2, dict]]:
    if "errorDescription" in response_dict:
        return response_dict["errorDescription"], cast(SendMessageErrorResponse_v1, response_dict)

    if "detail" in response_dict:
        msg = (response_dict.get("detail") or [{"msg": response_dict.get("internal_id", "unknown")}])[0].get("msg")
        return msg, cast(SendMessageErrorResponse_v2, response_dict)

    return "unknown", response_dict


class MeshRetry(Retry):
    """
    requests doesn't support disabling retry on an individual request, and to avoid creating duplicate messages
    we will not retry post requests to the base outbox url .... but other chunk posts are retryable
    """

    def increment(
        self,
        method: Optional[str] = None,
        url: Optional[str] = None,
        response: Optional[BaseHTTPResponse] = None,
        error: Optional[Exception] = None,
        _pool: Optional[ConnectionPool] = None,
        _stacktrace: Optional[TracebackType] = None,
    ) -> Retry:
        if method != "POST" or not url or not url.endswith("/outbox"):
            return super().increment(method, url, response, error, _pool, _stacktrace)

        if error:
            raise reraise(type(error), error, _stacktrace)

        if response and response.get_redirect_location():
            cause = "too many redirects"
        else:
            cause = ResponseError.GENERIC_ERROR
            if response and response.status:
                cause = ResponseError.SPECIFIC_ERROR.format(status_code=response.status)

        if _stacktrace:
            raise ResponseError(cause).with_traceback(_stacktrace)

        raise ResponseError(cause)


class SSLContextAdapter(HTTPAdapter):
    def __init__(
        self,
        cert: Optional[Union[Tuple[str], Tuple[str, str], Tuple[str, str, str]]] = None,
        verify: Optional[Union[str, bool]] = None,
        check_hostname: Optional[bool] = None,
        hostname_checks_common_name: Optional[bool] = None,
        max_retries: Union[int, Retry] = 0,
    ):
        self.cert = cert
        self.verify = verify
        self.check_hostname = check_hostname
        self.hostname_checks_common_name = hostname_checks_common_name

        super().__init__(max_retries=max_retries)

    def create_ssl_context(self) -> ssl.SSLContext:
        context = cast(ssl.SSLContext, create_urllib3_context())

        context.minimum_version = ssl.TLSVersion.TLSv1_2

        if self.cert and isinstance(self.cert, (tuple, list)):
            context.load_cert_chain(*self.cert)

        if self.verify:
            if isinstance(self.verify, (str, bytes)):
                context.load_verify_locations(self.verify)

            if self.check_hostname is not None:
                context.check_hostname = cast(bool, self.check_hostname)

            context.verify_mode = ssl.CERT_REQUIRED
            if context.check_hostname is not False and self.hostname_checks_common_name is not None:
                context.hostname_checks_common_name = self.hostname_checks_common_name

        if self.verify is False:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE

        return context

    def init_poolmanager(self, *args, **kwargs):
        context = self.create_ssl_context()
        kwargs["ssl_context"] = context
        if context.check_hostname is False:
            kwargs["assert_hostname"] = False
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, proxy, **proxy_kwargs):
        context = self.create_ssl_context()
        proxy_kwargs["ssl_context"] = context
        if context.check_hostname is False:
            proxy_kwargs["assert_hostname"] = False

        return super().proxy_manager_for(proxy, **proxy_kwargs)


class MeshClient:
    """
    A class representing a single MESH session, for a given user on a given
    endpoint. This class handles details such as chunking and compression
    transparently.
    """

    def __init__(  # noqa: C901
        self,
        url: Union[str, Endpoint],
        mailbox: str,
        password: str,
        shared_key: Optional[bytes] = None,
        cert: Optional[Union[Tuple[str], Tuple[str, str], Tuple[str, str, str]]] = None,
        verify: Optional[Union[str, bool]] = None,
        check_hostname: Optional[bool] = None,
        hostname_checks_common_name: Optional[bool] = None,
        max_chunk_size=75 * 1024 * 1024,
        proxies: Optional[Dict[str, str]] = None,
        transparent_compress: bool = False,
        max_retries: Union[int, Retry] = 3,
        retry_backoff_factor: Union[int, float] = 0.5,
        retry_status_force_list: Tuple[int, ...] = (425, 429, 502, 503, 504),
        retry_methods: Tuple[str, ...] = ("HEAD", "GET", "PUT", "POST", "DELETE", "OPTIONS", "TRACE"),
        timeout: Union[int, float] = 10 * 60,
    ):
        """
        Create a new MeshClient.

        At a minimum, you must provide an endpoint url, a mailbox and a
        password. The endpoint URL can either be a string, or a preconfigured
        endpoint. Currently, the following endpoints are preconfigured:

        INT_ENDPOINT
        LIVE_ENDPOINT
        DEP_ENDPOINT

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

        self._mailbox = mailbox
        self._max_chunk_size = max_chunk_size
        self._transparent_compress = transparent_compress
        self._timeout = timeout
        self._close_called = False

        self._session = requests.Session()

        if isinstance(url, str):
            endpoint_config = try_get_endpoint_from_url(url)
            if endpoint_config:
                url = endpoint_config

        self._url = (url.url if hasattr(url, "url") else url).rstrip("/")

        if verify is None and hasattr(url, "verify"):
            verify = url.verify

        if check_hostname is None and hasattr(url, "check_hostname"):
            check_hostname = url.check_hostname

        if hostname_checks_common_name is None and hasattr(url, "hostname_checks_common_name"):
            hostname_checks_common_name = url.hostname_checks_common_name

        if cert is None and hasattr(url, "cert"):
            cert = url.cert

        if verify is False:
            self._session.verify = False

        url_lower = self._url.lower()

        self._retries: Union[int, Retry] = 0
        if isinstance(max_retries, Retry):
            self._retries = max_retries
        elif max_retries:
            self._retries = MeshRetry(
                total=max_retries,
                backoff_factor=retry_backoff_factor,
                status_forcelist=retry_status_force_list,
                allowed_methods=retry_methods,
            )

        if url_lower.startswith("https://"):
            self._session.mount(
                self._url,
                SSLContextAdapter(cert, verify, check_hostname, hostname_checks_common_name, max_retries=self._retries),
            )
        else:
            self._session.mount(self._url, HTTPAdapter(max_retries=self._retries))

        if ".ncrs.nhs.uk" in url_lower:
            warnings.warn(
                "HSCN endpoints are being deprecated; please move to the internet endpoint.",
                category=DeprecationWarning,
                stacklevel=2,
            )

        self._session.headers = {
            "Accept": "application/vnd.mesh.v2+json",
            "User-Agent": (
                f"mesh_client;{__version__};N/A;{platform.processor() or platform.machine()};"
                f"{platform.system()};{platform.release()} {platform.version()}"
            ),
            "Accept-Encoding": "gzip",
        }

        self._session.auth = AuthTokenGenerator(shared_key, mailbox, password)

        self._session.proxies = proxies or {}

    @property
    def mailbox_path(self) -> str:
        return f"/messageexchange/{q(self._mailbox)}"

    @property
    def mailbox_url(self) -> str:
        return f"{self._url}{self.mailbox_path}"

    def ping(self) -> dict:
        """
        just connect to the _ping endpoint
        """
        response = self._session.get(f"{self._url}/messageexchange/_ping", timeout=self._timeout)

        response.raise_for_status()

        return cast(dict, response.json())

    def handshake(self):
        """
        connect and test authentication
        https://digital.nhs.uk/developer/api-catalogue/message-exchange-for-social-care-and-health-api#post-/messageexchange/-mailbox_id-
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
        https://digital.nhs.uk/developer/api-catalogue/message-exchange-for-social-care-and-health-api#get-/messageexchange/-mailbox_id-/count
        """
        response = self._session.get(f"{self.mailbox_url}/count", timeout=self._timeout)
        response.raise_for_status()
        return cast(int, response.json()["count"])

    def track_message(self, message_id: str) -> TrackingResponse_v2:
        """
        Gets tracking information from MESH about a message, by its  message id.
        Returns a dictionary, in much the same format that MESH provides it.
        https://digital.nhs.uk/developer/api-catalogue/message-exchange-for-social-care-and-health-api#get-/messageexchange/-mailbox_id-/outbox/tracking
        """
        url = f"{self.mailbox_url}/outbox/tracking?messageID={q(message_id)}"

        response = self._session.get(url, timeout=self._timeout)
        response.raise_for_status()
        return cast(TrackingResponse_v2, response.json())

    def lookup_endpoint(self, ods_code: str, workflow_id: str) -> EndpointLookupResponse_v2:
        """
        Lookup a mailbox by organisation code and workflow id.
        Returns a dictionary, in much the same format that MESH provides it.
        https://digital.nhs.uk/developer/api-catalogue/message-exchange-for-social-care-and-health-api#get-/messageexchange/endpointlookup/-ods_code-/-workflow_id-
        """
        response = self._session.get(
            f"{self._url}/messageexchange/endpointlookup/{q(ods_code)}/{q(workflow_id)}",
            timeout=self._timeout,
        )
        response.raise_for_status()
        return cast(EndpointLookupResponse_v2, response.json())

    def _inbox_v2_page(
        self, url: Optional[str] = None, params: Optional[Dict[str, Any]] = None
    ) -> ListMessageResponse_v2:
        url = url or f"{self.mailbox_url}/inbox"
        response = self._session.get(url, timeout=self._timeout, params=params)
        response.raise_for_status()

        return cast(ListMessageResponse_v2, response.json())

    def list_messages(self, max_results: Optional[int] = None, workflow_filter: Optional[str] = None) -> List[str]:
        """
            lists messages ids in the inbox; note if workflow_filter is set  it's possible to receive an empty page
            when more results exist outside the first max_results
            https://digital.nhs.uk/developer/api-catalogue/message-exchange-for-social-care-and-health-api#get-/messageexchange/-mailbox_id-/inbox

        Args:
            max_results (Optional[int]): optional max results to limit the page size
            workflow_filter (Optional[str]): workflow filter string

        Returns:
            List[str]: message ids
        """

        params: Dict[str, Union[str, int]] = {}
        if max_results:
            if max_results < 10:
                raise ValueError("if set max_results should be >= 10")
            params["max_results"] = max_results

        if workflow_filter:
            params["workflow_filter"] = workflow_filter

        result = self._inbox_v2_page(f"{self.mailbox_url}/inbox", params=params)

        return cast(List[str], result.get("messages", []))

    def retrieve_message(self, message_id: str) -> "Message":
        """
        Retrieve a message based on its message_id. This will return a Message object
        https://digital.nhs.uk/developer/api-catalogue/message-exchange-for-social-care-and-health-api#get-/messageexchange/-mailbox_id-/inbox/-message_id-
        """
        message_id = getattr(message_id, "_msg_id", message_id)
        response = self._session.get(f"{self.mailbox_url}/inbox/{q(message_id)}", stream=True, timeout=self._timeout)
        response.raise_for_status()
        return Message(message_id, response, self)

    def retrieve_message_chunk(self, message_id: str, chunk_num: Union[int, str]) -> Response:
        """
            get a chunk
            https://digital.nhs.uk/developer/api-catalogue/message-exchange-for-social-care-and-health-api#get-/messageexchange/-mailbox_id-/inbox/-message_id-/-chunk_number-
        Args:
            message_id (str): message id to receive
            chunk_num (int): chunk number

        Returns:
            Response: http response
        """
        response = self._session.get(
            f"{self.mailbox_url}/inbox/{q(message_id)}/{chunk_num}",
            stream=True,
            timeout=self._timeout,
        )
        response.raise_for_status()
        return response

    def send_message(  # noqa: C901
        self,
        recipient: str,
        data,
        max_chunk_size: Optional[int] = None,
        **kwargs,
    ) -> str:
        """
        Send a message to recipient containing data.

        https://digital.nhs.uk/developer/api-catalogue/message-exchange-for-social-care-and-health-api#post-/messageexchange/-mailbox_id-/outbox

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
                optional_args = ", ".join(["recipient", "data", *list(_OPTIONAL_HEADERS.keys())])
                raise TypeError(f"Unrecognised keyword argument '{key}'.  optional arguments are: {optional_args}")

        if transparent_compress:
            headers["Content-Encoding"] = "gzip"

        max_chunk_size = max_chunk_size or self._max_chunk_size
        chunks = SplitStream(data, max_chunk_size)
        headers["Mex-Chunk-Range"] = f"1:{len(chunks)}"

        chunk_iterator = iter(chunks)

        first_chunk = maybe_compressed(next(chunk_iterator))

        response1 = self._session.post(
            f"{self.mailbox_url}/outbox",
            data=first_chunk,
            headers=headers,
            timeout=self._timeout,
        )
        # MESH server dumps XML SOAP output on internal server error
        if response1.status_code >= 500:
            response1.raise_for_status()

        response_dict = response1.json()
        if _looks_like_send_error(response1.status_code, response_dict):
            msg, error_response = _get_send_error_message(response_dict)
            raise MeshError(msg, error_response)

        if response1.status_code not in (200, 202):
            raise MeshError(response_dict)

        success_response = cast(SendMessageResponse_v2, response_dict)

        message_id = success_response["message_id"]

        for chunk_num, chunk in enumerate(chunk_iterator, start=2):
            data = maybe_compressed(chunk)

            buffer = data
            if self._retries:
                # urllib3 body_pos requires a seekable stream to allow rewinding on retry
                buffer = BytesIO(data.read() if hasattr(data, "read") else data)

            headers = {
                "Content-Type": "application/octet-stream",
                "Mex-Chunk-Range": f"{chunk_num}:{len(chunks)}",
                "Mex-From": self._mailbox,
            }
            if transparent_compress:
                headers["Content-Encoding"] = "gzip"

            response = self._session.post(
                f"{self.mailbox_url}/outbox/{q(message_id)}/{chunk_num}",
                data=buffer,
                headers=headers,
                timeout=self._timeout,
            )

            # check other successful response codes
            if response.status_code in (200, 202):
                continue

            response.raise_for_status()

        return message_id

    def acknowledge_message(self, message_id: str):
        """
        Acknowledge a message_id, deleting it from MESH.
        https://digital.nhs.uk/developer/api-catalogue/message-exchange-for-social-care-and-health-api#put-/messageexchange/-mailbox_id-/inbox/-message_id-/status/acknowledged
        """
        message_id = getattr(message_id, "_msg_id", message_id)
        response = self._session.put(
            f"{self.mailbox_url}/inbox/{q(message_id)}/status/acknowledged",
            timeout=self._timeout,
        )
        response.raise_for_status()

    def iterate_message_ids(
        self, workflow_filter: Optional[str] = None, batch_size: Optional[int] = None
    ) -> Generator[str, None, None]:
        """
            generator lists messages ids in the inbox;

        Args:
            batch_size (Optional[int]): optional max results to limit the page size this will not limit the
            TOTAL results of the generator ... just limit the page size
            workflow_filter (Optional[str]): workflow filter string

        Returns:
            Generator[str]: message ids
        """

        params: Dict[str, Union[int, str]] = {}
        if batch_size:
            if batch_size < 10:
                raise ValueError("if set batch_size should be >= 10")
            params["max_results"] = batch_size

        if workflow_filter:
            params["workflow_filter"] = workflow_filter

        def _next_messages(page_result: ListMessageResponse_v2) -> Tuple[Optional[str], List[str]]:
            return cast(Dict[str, str], page_result.get("links", {})).get("next"), cast(
                List[str], page_result.get("messages", [])
            )

        result = self._inbox_v2_page(params=params)
        next_page, messages = _next_messages(result)
        yield from messages
        while next_page:
            result = self._inbox_v2_page(url=next_page)
            next_page, messages = _next_messages(result)
            yield from messages

    def iterate_messages(self, workflow_filter: Optional[str] = None, batch_size: Optional[int] = None):
        """
            generator lists messages ids in the inbox;
            Iterate over a list of Message objects for all messages in the user's
            inbox. This is provided as a convenience function, but will be
            slower than list_messages if only the message_ids are needed, since it
            will also begin to download messages.

        Args:
            batch_size (Optional[int]): optional max results to limit the page size
            workflow_filter (Optional[str]): workflow filter string

        Returns:
            Generator[Message]: messages in inbox
        """

        for msg_id in self.iterate_message_ids(workflow_filter=workflow_filter, batch_size=batch_size):
            yield self.retrieve_message(msg_id)

    def iterate_all_messages(self):
        """
            generator lists messages ids in the inbox;
            Iterate over a list of Message objects for all messages in the user's
            inbox. This is provided as a convenience function, but will be
            slower than list_messages if only the message_ids are needed, since it
            will also begin to download messages.

        Args:
            page_size (Optional[int]): optional max results to limit the page size, will not limit the tota

        Returns:
            Generator[Message]: messages in inbox
        """

        for msg_id in self.iterate_message_ids():
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
                " on this occasion, but you should not rely on this.",
                stacklevel=2,
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

        def maybe_decompress(resp):
            return GzipDecompressStream(resp.raw) if resp.headers.get("Content-Encoding") == "gzip" else resp.raw

        self._response = CombineStreams(
            chain(
                [maybe_decompress(response)],
                (maybe_decompress(client.retrieve_message_chunk(msg_id, str(i + 2))) for i in range(chunk_count - 1)),
            )
        )

    def id(self) -> str:  # noqa: A003
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


class AuthTokenGenerator:
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
