#!/usr/bin/python3
"""
A crude mock implementation of the MESH API, suitable for use in
small-scale tests. This file can either be run as a script, which will serve
on port 8000, or used as a test fixture, which will serve on a random port.

To run mock mesh as a script, run:

python -m mesh_client.mock_server

This mock instance will use TLS mutual authentication, with hard-coded SSL
certs that are included in the distribution. Matching client certs are
also included, and the settings to use them are included in the mesh_client
package as default_ssl_opts. Since these certs and keys are publicly available,
they should only be used in test environments.
"""
from __future__ import print_function, absolute_import
import datetime
import hmac
import json
import os.path
import random
import ssl
import time
import traceback
import zlib
from contextlib import closing
from hashlib import sha256
from collections import OrderedDict
from threading import Thread
from wsgiref.util import shift_path_info
from wsgiref.simple_server import make_server, WSGIServer
from .io_helpers import stream_from_wsgi_environ
from .key_helper import get_shared_key_from_environ

_OPTIONAL_HEADERS = {
    "HTTP_CONTENT_ENCODING": "Content-Encoding",
    "HTTP_MEX_WORKFLOWID": "Mex-WorkflowID",
    "HTTP_MEX_FILENAME": "Mex-FileName",
    "HTTP_MEX_LOCALID": "Mex-LocalID",
    "HTTP_MEX_MESSAGETYPE": "Mex-MessageType",
    "HTTP_MEX_PROCESSID": "Mex-ProcessID",
    "HTTP_MEX_PROCESSLID": "Mex-ProcesslID",
    "HTTP_MEX_SUBJECT": "Mex-Subject",
    "HTTP_MEX_CONTENT_ENCRYPTED": "Mex-Content-Encrypted",
    "HTTP_MEX_CONTENT_COMPRESS": "Mex-Content-Compress",
    "HTTP_MEX_CONTENT_CHECKSUM": "Mex-Content-Checksum",
    "HTTP_MEX_COMPRESSED": "Mex-Compressed",
    "HTTP_MEX_CONTENT_COMPRESSED": "Mex-Content-Compressed",
    "HTTP_MEX_CHUNK_RANGE": "Mex-Chunk-Range",
    "HTTP_MEX_FROM": "Mex-From",
    "HTTP_MEX_TO": "Mex-To"
}


TIMESTAMP_FORMAT = '%Y%m%d%H%M%S%f'


def _dumb_response_code(code, message):
    def handle(environ, start_response):
        start_response("{} {}".format(code, message),
                       [("Content-Type", "text/plain")])
        return [message.encode("UTF-8")]

    return handle


_not_found = _dumb_response_code(404, "Not Found")
_not_authorized = _dumb_response_code(401, "Unauthorized")
_forbidden = _dumb_response_code(403, "Forbidden")
_simple_ok = _dumb_response_code(200, "OK")
_bad_request = _dumb_response_code(400, "Bad Request")
_server_error = _dumb_response_code(500, "Server Error")


def _ok(content_type, data, start_response):
    start_response("200 OK", [("Content-Type", content_type)])
    return data


def _error(content_type, data, start_error_response):
    start_error_response("500 INTERNAL SERVER ERROR", [("Content-Type", content_type)])
    return data


def _compose(**kwargs):
    def handle(environ, start_response):
        path_component = shift_path_info(environ) or 'default'
        if path_component in kwargs:
            return kwargs[path_component](environ, start_response)
        else:
            return _not_found(environ, start_response)

    return handle


class MockMeshApplication:
    """
    A crude mock instance of MESH, suitable for use in tests.

    This class can be used as a context manager:

    with MockMeshApplication() as app:
        uri = app.uri
        # Send and receive stuff from MESH endpoint at uri
        assert app.messages == expectedMessages

    This will spin up a MESH instance on a random port, and make its uri
    available as app.uri. The instance will be shut down when the context
    manager exits. These capabilities are also available as start_server and
    stop_server, for use in cases where context managers are not convenient.

    Subclasses may wish to override make_message_id, to allow testing with
    different message id formats.
    """

    def __init__(self, shared_key=get_shared_key_from_environ()):
        self.messages = {}
        self._shared_key = shared_key
        self._msg_count = 0

    @property
    def __call__(self):
        return _compose(
            messageexchange=self.message_exchange,
            endpointlookup=_compose(
                mesh=self.endpoint_lookup
            )
        )

    def authenticated(self, handler):
        def handle(environ, start_response):
            requested_mailbox = shift_path_info(environ)
            authorization_header = environ.get("HTTP_AUTHORIZATION", "")
            if not authorization_header.startswith("NHSMESH "):
                return _not_authorized(environ, start_response)

            auth_data = authorization_header[8:]
            mailbox, nonce, nonce_count, ts, hashed = auth_data.split(":")
            expected_password = "password"
            hash_data = ":".join([
                mailbox, nonce, nonce_count, expected_password, ts
            ])
            myhash = hmac.HMAC(self._shared_key, hash_data.encode("ASCII"),
                               sha256).hexdigest()
            if myhash == hashed and mailbox == requested_mailbox:
                environ["mesh.mailbox"] = mailbox
                return handler(environ, start_response)
            else:
                return _forbidden(environ, start_response)

        return handle

    def handshake(self, environ, start_response):
        auth_headers = [
            'HTTP_MEX_CLIENTVERSION',
            'HTTP_MEX_JAVAVERSION',
            'HTTP_MEX_OSARCHITECTURE',
            'HTTP_MEX_OSNAME',
            'HTTP_MEX_OSVERSION'
        ]
        for auth_header in auth_headers:
            if auth_header not in environ:
                return _server_error(environ, start_response)
        mailbox_id = environ["mesh.mailbox"]
        return _ok('application/json',
                   [json.dumps({"mailboxId": mailbox_id}).encode("UTF-8")],
                   start_response)

    @property
    def message_exchange(self):
        return self.authenticated(
            _compose(
                inbox=self.inbox,
                outbox=self.outbox,
                count=self.count,
                default=self.handshake
            )
        )


    def inbox(self, environ, start_response):
        request_method = environ["REQUEST_METHOD"]
        message_id = shift_path_info(environ)
        mailbox = environ["mesh.mailbox"]

        if (request_method == "PUT" and
                environ["PATH_INFO"] == "/status/acknowledged"):
            del self.messages[mailbox][message_id]
            return _simple_ok(environ, start_response)

        if request_method == "GET":
            if message_id:
                chunk_num = shift_path_info(environ)
                if chunk_num:
                    return self.download_chunk(
                        message_id, chunk_num)(environ, start_response)
                message = self.messages[message_id]
                if message['headers']['Mex-To'] != mailbox:
                    return _not_found(environ, start_response)
                response_code = ("206 Partial Content"
                                 if "chunks" in message else "200 OK")
                start_response(response_code, list(message["headers"].items()))
                return [message["data"]]
            else:
                messages = {"messages": list(
                    self.messages.get(mailbox, {}).keys())}
                return _ok("application/json",
                           [json.dumps(messages).encode("UTF-8")],
                           start_response)
        else:
            return _bad_request(environ, start_response)

    def count(self, environ, start_response):
        request_method = environ["REQUEST_METHOD"]
        mailbox = environ["mesh.mailbox"]
        if request_method == "GET":
            result = {
                "count": len(self.messages.get(mailbox, {})),
                "internalID": "12345",
                "allResultsIncluded": True,

            }
            return _ok("application/json",
                       [json.dumps(result).encode("UTF-8")],
                       start_response)
        else:
            return _bad_request(environ, start_response)

    def outbox(self, environ, start_response):
        chunk_msg = shift_path_info(environ)
        if chunk_msg == 'tracking':
            return self.tracking(environ, start_response)
        if chunk_msg:
            return self.upload_chunk(chunk_msg)(environ, start_response)
        try:
            recipient = environ["HTTP_MEX_TO"]
            sender = environ["HTTP_MEX_FROM"]
            mailbox_id = environ["mesh.mailbox"]
            assert mailbox_id == sender
        except Exception as e:
            traceback.print_exc()
            start_response("417 Expectation Failed",
                           [('Content-Type', 'application/json')])
            return [json.dumps({
                "errorCode": "02",
                "errorDescription": str(e),
                "errorEvent": "COLLECT",
                "messageID": "99999"
            })]

        mailbox = self.messages.setdefault(recipient, OrderedDict())
        with closing(stream_from_wsgi_environ(environ)) as stream:
            data = stream.read()
        if not data:
            start_response("417 Expectation Failed",
                           [('Content-Type', 'application/json')])
            return [json.dumps({
                "errorCode": "02",
                "errorDescription": "Data file is missing or inaccessible.",
                "errorEvent": "COLLECT",
                "messageID": "99999"
            }).encode("utf-8")]
        headers = {_OPTIONAL_HEADERS[key]: value
                   for key, value in environ.items()
                   if key in _OPTIONAL_HEADERS}
        msg_id = self.make_message_id()
        headers['Mex-MessageID'] = msg_id
        mailbox[msg_id] = {"headers": headers, "data": data}
        self.messages[msg_id] = mailbox[msg_id]
        return _ok("application/json",
                   [json.dumps({"messageID": msg_id}).encode("UTF-8")],
                   start_response)

    def upload_chunk(self, chunk_msg):
        def handle(environ, start_response):
            chunk_num = shift_path_info(environ)
            msg = self.messages[chunk_msg]
            chunks = msg.setdefault("chunks", {})
            with closing(stream_from_wsgi_environ(environ)) as stream:
                data = stream.read()
            chunks[chunk_num] = zlib.compress(data) if not environ.get('HTTP_CONTENT_ENCODING', None) else data
            start_response('202 Accepted', [])
            return []

        return handle

    def download_chunk(self, chunk_msg, chunk_num):
        def handle(environ, start_response):
            msg = self.messages[chunk_msg]
            chunks = msg["chunks"]
            chunk = chunks[chunk_num]
            if environ['HTTP_ACCEPT_ENCODING'] != "gzip":
                chunk = zlib.decompress(chunk)

            chunk_header = "{}:{}".format(chunk_num, len(chunks) + 1)
            start_response('200 OK', [
                ('Content-Type', 'application/octet-stream'),
                ('Content-Encoding', 'gzip'),
                ('Mex-Chunk-Range', chunk_header)
            ])
            return [chunk]

        return handle

    def tracking(self, environ, start_response):
        tracking_id = shift_path_info(environ)
        if not tracking_id:
            return _bad_request(environ, start_response)
        for message in self.messages.values():
            if message.get('headers', {}).get('Mex-LocalID') == tracking_id:
                headers = message['headers']
                recipient = headers['Mex-To']
                message_id = headers['Mex-MessageID']
                acked = message_id not in self.messages[recipient]
                now = datetime.datetime.now().strftime(TIMESTAMP_FORMAT)
                response = {
                    "localId": tracking_id,
                    "dtsId": message_id,
                    "messageType": "DATA",
                    "chunkCount": len(message['chunks']),
                    "subject": headers.get('Mex-Subject'),
                    "statusEvent": None,
                    "version": "1.0",
                    "downloadTimestamp": now,
                    "statusDescription": None,
                    "status": "Acknowledged" if acked else "Accepted",
                    "workflowId": headers.get('Mex-WorkflowID'),
                    "fileName": headers.get('Mex-FileName'),
                    "uploadTimestamp": now,
                    "recipient": headers['Mex-To'],
                    "sender": headers['Mex-From'],
                    "messageId": message_id,
                    "fileSize": 0
                }
                return _ok('application/json',
                           [json.dumps(response).encode('UTF-8')],
                           start_response)
        else:
            return _not_found(environ, start_response)

    def endpoint_lookup(self, environ, start_response):
        org_code = shift_path_info(environ)
        workflow_id = shift_path_info(environ)
        if not org_code or not workflow_id:
            return _not_found(environ, start_response)
        result = {
            "query_id": "{ts:%Y%m%d%H%M%S%f}_{rnd:06x}_{ts:%s}".format(
                ts=datetime.datetime.now(),
                rnd=random.randint(0, 0xffffff)),
            "results": [
                {
                    "address": "{}HC001".format(org_code),
                    "description": "{} {} endpoint".format(org_code, workflow_id),
                    "endpoint_type": "MESH"
                }
            ]
        }
        return _ok('application/json',
                   [json.dumps(result).encode('UTF-8')],
                   start_response)

    def make_message_id(self):
        """
        Create a new message id. By default, this uses roughly the same format
        as MESH (although the format is undocumented), but it can be overridden
        in subclasses for different behaviour
        """
        n = self._msg_count
        self._msg_count += 1
        return "{ts:%Y%m%d%H%M%S%f}_{num:06d}".format(
            ts=datetime.datetime.now(),
            num=n
        )

    def __enter__(self):
        self.start_server()
        return self

    def __exit__(self, ex_type, value, tb):
        self.stop_server()

    def start_server(self):
        """
        Start an embedded web server, running the mock MESH app. After running
        this method, the uri of the running MESH instance will be available
        as self.uri
        """
        self.server = make_server("", 0, self, server_class=SSLWSGIServer)
        port = self.server.server_address[1]
        self.uri = "https://localhost:{}".format(port)
        thread = Thread(
            target=self.server.serve_forever,
            kwargs={"poll_interval": 0.01})
        thread.daemon = True
        thread.start()
        return self

    def stop_server(self):
        """
        Stop a server that was started by start_server(). This has no effect
        when the app is run from an external WSGI container, such as uWSGI,
        GUnicorn or Cheroot.
        """
        self.server.shutdown()


class MockMeshChunkRetryApplication(MockMeshApplication, object):
    def __init__(self):
        self.allowed_retries = {}
        super(MockMeshChunkRetryApplication, self).__init__()

    def set_chunk_retry_options(self, options):
        self.retry_options = options

    def outbox(self, environ, start_response):
        current_chunk = int(environ['HTTP_MEX_CHUNK_RANGE'].split(':')[0])
        if current_chunk == 1:
            self.allowed_retries = {p[0]: p[1] for p in self.retry_options}

        if current_chunk in self.allowed_retries:
            if self.allowed_retries[current_chunk] >= 0:
                self.allowed_retries[current_chunk] -= 1
                return _error("application/json", '', start_response)

        return super(MockMeshChunkRetryApplication, self).outbox(environ, start_response)


class SlowMockMeshApplication(MockMeshApplication):
    def __call__(self, environ, start_response):
        time.sleep(2.0)
        return super(SlowMockMeshApplication, self).__call__(environ, start_response)


_data_dir = os.path.dirname(__file__)
default_server_context = ssl.create_default_context(
    ssl.Purpose.CLIENT_AUTH, cafile=os.path.join(_data_dir, "ca.cert.pem"))
default_server_context.load_cert_chain(
    os.path.join(_data_dir, 'server.cert.pem'),
    os.path.join(_data_dir, 'server.key.pem'))
default_server_context.check_hostname = False
default_server_context.verify_mode = ssl.CERT_REQUIRED


class SSLWSGIServer(WSGIServer, object):
    __context = default_server_context

    def get_request(self):
        (socket, addr) = super(SSLWSGIServer, self).get_request()
        return self.__context.wrap_socket(socket, server_side=True), addr


def main():
    print("Serving on port 8000")
    server = make_server(
        "", 8000, MockMeshApplication(), server_class=SSLWSGIServer)
    server.serve_forever(0.01)


if __name__ == "__main__":
    main()
