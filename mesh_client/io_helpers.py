from __future__ import division
import io
import os
import zlib
import six


class IteratorMixin(object):
    """
    Produce a series of lines, from a readable that only exposes a `read` method
    """
    __block_size = 65536
    __line_iterator = None

    def __iter__(self):
        # We use a BytesIO as our buffer, so we can piggyback on its readlines method
        buff = io.BytesIO()
        while True:
            block = self.read(self.__block_size)
            buff.write(block)
            last_block = len(block) == 0
            buff.seek(0)
            lines = buff.readlines()
            for line in lines[:-1]:
                yield line
            if not last_block:
                buff.seek(0)
                buff.write(lines[-1])
                buff.truncate()
            else:
                yield lines[-1]
                break

    def readline(self):
        if not self.__line_iterator:
            self.__line_iterator = iter(self)
        try:
            return six.next(self.__line_iterator)
        except StopIteration:
            return b''

    def readlines(self):
        return list(iter(self))


class CloseUnderlyingMixin(object):
    def close(self):
        try:
            if hasattr(self._underlying, "close"):
                self._underlying.close()
        finally:
            self._underlying = None
            if hasattr(super(CloseUnderlyingMixin, self), "close"):
                super(CloseUnderlyingMixin, self).close()

    def __del__(self):
        self.close()
        if hasattr(super(CloseUnderlyingMixin, self), "__del__"):
            super(CloseUnderlyingMixin, self).__del__()

    def __enter__(self):
        if hasattr(super(CloseUnderlyingMixin, self), "__enter__"):
            return super(CloseUnderlyingMixin, self).__enter__()
        else:
            return self

    def __exit__(self, typ, value, traceback):
        self.close()
        if hasattr(super(CloseUnderlyingMixin, self), "__exit__"):
            return super(CloseUnderlyingMixin, self).__exit__(typ, value,
                                                              traceback)


class AbstractGzipStream(IteratorMixin, CloseUnderlyingMixin):
    """
    Wrap an existing readable, in a readable that produces a gzipped
    version of the underlying stream.
    """

    def __init__(self, underlying, block_size=65536):
        self._underlying = underlying
        self._buffer = io.BytesIO()
        self._block_size = block_size

    def _process_block(self, block):
        raise NotImplementedError()

    def _finish(self):
        raise NotImplementedError()

    def read(self, n=-1):
        if n == -1:
            n = None
        while True:
            # If underlying stream finished, just read from buffer
            if self._underlying is None:
                return self._buffer.read(n)

            # If underlying stream not finished, buffer is positioned at end,
            # ready for writing
            limit = self._buffer.tell()
            if n is not None and n != -1 and limit >= n:
                self._buffer.seek(0)
                try:
                    return self._buffer.read(n)
                finally:
                    remainder = self._buffer.read(limit - n)
                    self._buffer = io.BytesIO(remainder)
                    self._buffer.seek(0, 2)
            else:
                next_block = self._underlying.read(self._block_size)
                if len(next_block) > 0:
                    self._buffer.write(self._process_block(next_block))
                else:
                    self._buffer.write(self._finish())
                    self._buffer.seek(0)
                    self.close()

    def read_all(self):
        self.read()


class GzipCompressStream(AbstractGzipStream):
    """
    Wrap an existing readable, in a readable that produces a gzipped
    version of the underlying stream.
    """

    def __init__(self, underlying, block_size=65536):
        AbstractGzipStream.__init__(self, underlying, block_size)
        self._compress_obj = zlib.compressobj(
            9,  # level
            zlib.DEFLATED,  # method
            31  # wbits - gzip header, maximum window
        )

    def _process_block(self, block):
        return self._compress_obj.compress(block)

    def _finish(self):
        return self._compress_obj.flush(zlib.Z_FINISH)


class GzipDecompressStream(AbstractGzipStream):
    """
    Wrap an existing readable, in a readable that decompresses
    the underlying stream.
    """

    def __init__(self, underlying, block_size=65536):
        AbstractGzipStream.__init__(self, underlying, block_size)
        self._decompress_obj = zlib.decompressobj(
            47  # wbits - detect header, maximum window
        )

    def _process_block(self, block):
        return self._decompress_obj.decompress(block)

    def _finish(self):
        return self._decompress_obj.flush()


class SplitStream(CloseUnderlyingMixin):
    def __init__(self, data, chunk_size=75 * 1024 * 1024):
        if isinstance(data, bytes):
            self._underlying = io.BytesIO(data)
            self._length = len(data)
        elif hasattr(data, "info"):
            self._underlying = data
            self._length = int(data.info()["Content-Length"])
        elif hasattr(data, "fileno"):
            self._underlying = data
            self._length = os.fstat(data.fileno()).st_size
        elif hasattr(data, "_content_length"):
            self._underlying = data
            self._length = data._content_length
        elif isinstance(data, dict) and "Body" in data and "ContentLength" in data:
            self._underlying = data["Body"]
            self._length = data["ContentLength"]
        else:
            raise TypeError("data must be a bytes, file, or urllib response")
        self._chunk_size = chunk_size
        self._remaining = 0

    def __len__(self):
        return max(1,
                   (self._length + self._chunk_size - 1) // self._chunk_size)

    def __iter__(self):
        for i in range(len(self)):
            self._underlying.read(self._remaining)
            self._remaining = min(self._chunk_size,
                                  self._length - i * self._chunk_size)
            yield _SplitChunk(self)


class _SplitChunk(IteratorMixin):
    def __init__(self, owner):
        self._owner = owner

    def read(self, n=-1):
        if n == -1:
            n = None
        if n is None or n > self._owner._remaining:
            n = self._owner._remaining
        try:
            return self._owner._underlying.read(n)
        finally:
            self._owner._remaining -= n

    def __len__(self):
        return self._owner._remaining


class CombineStreams(IteratorMixin):
    def __init__(self, streams):
        self._streams = iter(streams)
        self._current_stream = six.next(self._streams)

    def read(self, n=-1):
        if n == -1:
            n = None
        result = io.BytesIO()
        try:
            while True:
                result.write(self._current_stream.read(n))
                if n is None or result.tell() < n:
                    self._close_current_stream()
                    self._current_stream = six.next(self._streams)
                else:
                    return result.getvalue()
        except StopIteration:
            self._current_stream = io.BytesIO()  # Empty stream
            return result.getvalue()

    def close(self):
        self._close_current_stream()

    def _close_current_stream(self):
        try:
            self._current_stream.close()
        except:
            pass


class FiniteLengthStream(IteratorMixin, CloseUnderlyingMixin):
    def __init__(self, stream, length):
        self._underlying = stream
        self._remaining = length

    def read(self, n=-1):
        if n == -1 or n is None:
            n = self._remaining
        n = min(n, self._remaining)
        try:
            return self._underlying.read(n)
        finally:
            self._remaining -= n


class ChunkedStream(IteratorMixin, CloseUnderlyingMixin):
    def __init__(self, underlying):
        self._underlying = underlying
        self._buffer = io.BytesIO()

    def read(self, n=-1):
        if n == -1:
            n = None
        while True:
            # If underlying stream finished, just read from buffer
            if self._underlying is None:
                return self._buffer.read(n)

            # If underlying stream not finished, buffer is positioned at end,
            # ready for writing
            limit = self._buffer.tell()
            if n is not None and limit >= n:
                self._buffer.seek(0)
                try:
                    return self._buffer.read(n)
                finally:
                    remainder = self._buffer.read(limit - n)
                    self._buffer = io.BytesIO(remainder)
                    self._buffer.seek(0, 2)
            else:
                block_header = self._underlying.read(1)
                while not block_header.endswith(b"\r\n"):
                    block_header += self._underlying.read(1)
                block_length = int(block_header, 16)
                if block_length > 0:
                    self._buffer.write(self._underlying.read(block_length))
                    assert self._underlying.read(2) == b"\r\n"
                else:
                    self._buffer.seek(0)
                    self._underlying.close()
                    self._underlying = None


def stream_from_wsgi_environ(environ):
    if environ.get("CONTENT_LENGTH"):
        return FiniteLengthStream(environ["wsgi.input"],
                                  int(environ["CONTENT_LENGTH"]))
    elif environ.get("HTTP_TRANSFER_ENCODING") == "chunked":
        return ChunkedStream(environ["wsgi.input"])
    else:
        # terminated by close
        return environ["wsgi.input"]
