from __future__ import division
import io
import itertools
import mmap
import os
import zlib
import six


class GzipInputStream(object):
    """
    Wrap an existing readable, in a readable that produces a gzipped
    version of the underlying stream.
    """
    def __init__(self, underlying, block_size=65536):
        self._underlying = underlying
        self._compress_obj = zlib.compressobj(
            9,  # level
            zlib.DEFLATED,  # method
            31  # wbits - gzip header, maximum window
        )
        self._buffer = io.BytesIO()
        self._block_size = block_size

    def read(self, n=-1):
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
                    self._buffer.write(self._compress_obj.compress(next_block))
                else:
                    self._buffer.write(self._compress_obj.flush(zlib.Z_FINISH))
                    self._buffer.seek(0)
                    self._underlying.close()
                    self._underlying = None

    def read_all(self):
        self.read()

    def close(self):
        if self._underlying is not None:
            self._underlying.close()
            self._underlying = None

    def __del__(self):
        self.close()

    def __enter__(self):
        return self

    def __exit__(self, typ, value, traceback):
        self.close()


class SplitFile(object):
    def __init__(self, f, chunk_size=75 * 1024 * 1024):
        self._fd = f.fileno()
        self._chunk_size = ((chunk_size // mmap.ALLOCATIONGRANULARITY)
                            * mmap.ALLOCATIONGRANULARITY)

    def __len__(self):
        return ((os.fstat(self._fd).st_size + self._chunk_size - 1)
                // self._chunk_size)

    def __iter__(self):
        size = os.fstat(self._fd).st_size
        for i in itertools.count():
            if i * self._chunk_size >= size:
                break
            chunk_start = i * self._chunk_size
            current_chunk_size = min(self._chunk_size, size - chunk_start)
            m = mmap.mmap(self._fd, current_chunk_size,
                          access=mmap.ACCESS_READ, offset=chunk_start)
            try:
                yield m
            finally:
                m.close()


class SplitBytes(object):
    def __init__(self, data, chunk_size=75 * 1024 * 1024):
        self._data = data
        self._chunk_size = chunk_size

    def __len__(self):
        return ((len(self._data) + self._chunk_size - 1)
                // self._chunk_size)

    def __iter__(self):
        size = len(self._data)
        for i in itertools.count():
            if i * self._chunk_size >= size:
                break
            chunk_start = i * self._chunk_size
            current_chunk_size = min(self._chunk_size, size - chunk_start)
            yield io.BytesIO(
                self._data[chunk_start:chunk_start + current_chunk_size])


class CombineStreams(object):
    def __init__(self, streams):
        self._streams = iter(streams)
        self._current_stream = six.next(self._streams)

    def read(self, n=-1):
        result = io.BytesIO()
        try:
            while True:
                result.write(self._current_stream.read(n))
                if n == -1 or n is None or result.tell() < n:
                    self._current_stream = six.next(self._streams)
                else:
                    return result.getvalue()
        except StopIteration:
            return result.getvalue()
