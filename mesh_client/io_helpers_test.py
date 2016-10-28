from __future__ import absolute_import
from unittest import TestCase, main
import io
import gzip
from .io_helpers import GzipInputStream


class IOHelpersTest(TestCase):
    def test_gzip_input_stream(self):
        underlying = io.BytesIO(b"This is a short test stream")
        instance = GzipInputStream(underlying, block_size=4)
        result = b""
        for i in range(1000):
            read_result = instance.read(i)
            result += read_result
            if len(read_result) < i:
                break
        self.assertEqual(b"", instance.read(10))
        self.assertEqual(b"", instance.read())

        # Decode with GzipFile
        test_decoder = gzip.GzipFile('', mode='r', fileobj=io.BytesIO(result))
        self.assertEqual(b"This is a short test stream", test_decoder.read())

    def test_gzip_input_stream_read_all(self):
        underlying = io.BytesIO(b"This is a short test stream")
        instance = GzipInputStream(underlying, block_size=4)
        result = instance.read()
        self.assertEqual(b"", instance.read(10))
        self.assertEqual(b"", instance.read())

        # Decode with GzipFile
        test_decoder = gzip.GzipFile('', mode='r', fileobj=io.BytesIO(result))
        self.assertEqual(b"This is a short test stream", test_decoder.read())

if __name__ == '__main__':
    main()
