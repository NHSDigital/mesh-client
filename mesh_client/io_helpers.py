import io
import zlib


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
