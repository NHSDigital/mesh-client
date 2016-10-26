#!/usr/bin/python3
import hmac
import json
import uuid
import ssl
import random
import traceback
from hashlib import sha256
from threading import Thread
from wsgiref.util import shift_path_info
from wsgiref.simple_server import make_server, WSGIServer


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


def _ok(content_type, data, start_response):
    start_response("200 OK", [("Content-Type", content_type)])
    return data


def _compose(**kwargs):
    def handle(environ, start_response):
        path_component = shift_path_info(environ)
        if path_component in kwargs:
            return kwargs[path_component](environ, start_response)
        else:
            return _not_found(environ, start_response)
    return handle


class MockMeshApplication:
    def __init__(self, shared_key=b"BackBone"):
        self.messages = {}
        self._shared_key = shared_key

    @property
    def __call__(self):
        return _compose(messageexchange=self.message_exchange)

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
            myhash = hmac.HMAC(
                self._shared_key,
                hash_data.encode("ASCII"),
                sha256
            ).hexdigest()
            if myhash == hashed and mailbox == requested_mailbox:
                environ["mesh.mailbox"] = mailbox
                return handler(environ, start_response)
            else:
                return _forbidden(environ, start_response)
        return handle

    @property
    def message_exchange(self):

        return self.authenticated(_compose(
            inbox=self.inbox,
            outbox=self.outbox
        ))

    def inbox(self, environ, start_response):
        request_method = environ["REQUEST_METHOD"]
        message_id = shift_path_info(environ)
        mailbox = environ["mesh.mailbox"]
        if request_method == "GET":
            if message_id:
                message = self.messages[mailbox][message_id]
                return _ok(
                    "application/octet-stream",
                    [message], start_response)
            else:
                messages = {"messages": list(self.messages[mailbox].keys())}
                return _ok(
                    "application/json",
                    [json.dumps(messages).encode("UTF-8")], start_response)
        elif (request_method == "PUT"
              and environ["PATH_INFO"] == "/status/acknowledged"):
            del self.messages[mailbox][message_id]
            return _simple_ok(environ, start_response)
        else:
            return _bad_request(environ, start_response)

    def outbox(self, environ, start_response):
        try:
            recipient = environ["HTTP_MEX_TO"]
            sender = environ["HTTP_MEX_FROM"]
            mailbox_id = environ["mesh.mailbox"]
            assert mailbox_id == sender
        except Exception:
            traceback.print_exc()
            start_response("417 Expectation Failed",
                           [("Content-Type", "text/plain")])
            return [b"Expectation failed -"
                    b" Mex-From and Mex-To headers required"]

        mailbox = self.messages.setdefault(recipient, {})
        content_length = environ.get("CONTENT_LENGTH")
        input_ = environ["wsgi.input"]
        data = (input_.read(int(content_length)) if content_length
                else input_.read())
        msg_id = str(uuid.uuid4())
        mailbox[msg_id] = data
        return _ok(
            "application/json",
            [json.dumps({"messageID": msg_id}).encode("UTF-8")],
            start_response
        )

    def __enter__(self):
        port = random.randint(32768, 65535)
        self.uri = "https://localhost:{}".format(port)
        self.server = make_server("", port, self, server_class=SSLWSGIServer)
        Thread(target=self.server.serve_forever).start()

    def __exit__(self, type, value, traceback):
        self.server.shutdown()


class SSLWSGIServer(WSGIServer):
    __context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH,
                                           cafile="ca.cert.pem")
    __context.load_cert_chain('server.cert.pem', 'server.key.pem')
    __context.check_hostname = False
    __context.verify_mode = ssl.CERT_REQUIRED

    def get_request(self):
        (socket, addr) = super().get_request()
        return (self.__context.wrap_socket(socket, server_side=True), addr)


if __name__ == "__main__":
    print("Serving on port 8000")
    server = make_server("", 8000, MockMeshApplication(),
                         server_class=SSLWSGIServer)
    server.serve_forever()
