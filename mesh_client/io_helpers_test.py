from __future__ import absolute_import, print_function
from unittest import TestCase, main
import io
import gzip
import six
import tempfile
from .io_helpers import GzipCompressStream, GzipDecompressStream, \
    CombineStreams, SplitStream, IteratorMixin
from six.moves.urllib.parse import urljoin
from six.moves.urllib.request import pathname2url, urlopen
from contextlib import closing


def path2url(path):
    return urljoin('file:', pathname2url(path))


try:
    from itertools import izip
except ImportError:
    izip = zip

mebibyte = 1024 * 1024
small_chunk = 10


class FakeMixinUser(IteratorMixin):
    def __init__(self, data, block_size):
        self.backing_buffer = io.BytesIO(data)
        self._IteratorMixin__block_size = block_size

    def read(self, n):
        return self.backing_buffer.read(n)

MIXIN_DATA = b"""a
aa
aaa
aaaa
aaaaa
aaaaaa
"""


class IOHelpersTest(TestCase):
    def test_gzip_compress_stream(self):
        underlying = io.BytesIO(b"This is a short test stream")
        instance = GzipCompressStream(underlying, block_size=4)
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

    def test_gzip_compress_stream_read_all(self):
        underlying = io.BytesIO(b"This is a short test stream")
        instance = GzipCompressStream(underlying, block_size=4)
        result = instance.read()
        self.assertEqual(b"", instance.read(10))
        self.assertEqual(b"", instance.read())

        # Decode with GzipFile
        test_decoder = gzip.GzipFile('', mode='r', fileobj=io.BytesIO(result))
        self.assertEqual(b"This is a short test stream", test_decoder.read())

    def test_gzip_decompress_stream(self):
        underlying = io.BytesIO()
        gzwriter = gzip.GzipFile(fileobj=underlying, mode='w')
        gzwriter.write(b"This is a short test stream")
        gzwriter.close()
        underlying.seek(0)

        instance = GzipDecompressStream(underlying, block_size=4)
        result = b""
        for i in range(1000):
            read_result = instance.read(i)
            result += read_result
            if len(read_result) < i:
                break
        self.assertEqual(b"", instance.read(10))
        self.assertEqual(b"", instance.read())

        self.assertEqual(b"This is a short test stream", result)

    def test_gzip_decompress_stream_read_all(self):
        underlying = io.BytesIO()
        gzwriter = gzip.GzipFile(fileobj=underlying, mode='w')
        gzwriter.write(b"This is a short test stream")
        gzwriter.close()
        underlying.seek(0)

        instance = GzipDecompressStream(underlying, block_size=4)
        result = instance.read()
        self.assertEqual(b"", instance.read(10))
        self.assertEqual(b"", instance.read())

        self.assertEqual(b"This is a short test stream", result)

    def test_split_file(self):
        with tempfile.TemporaryFile() as f:
            f.write(b"a" * mebibyte)
            f.write(b"b" * mebibyte)
            f.flush()
            f.seek(0)
            instance = SplitStream(f, mebibyte)
            self.assertEqual(len(instance), 2)
            for m, c in izip(instance, [b"a", b"b"]):
                self.assertEqual(m.read(mebibyte), c * mebibyte)

    def test_split_file_irregular_size(self):
        with tempfile.TemporaryFile() as f:
            f.write(b"a" * mebibyte)
            f.write(b"b")
            f.flush()
            f.seek(0)
            instance = SplitStream(f, mebibyte)
            self.assertEqual(len(instance), 2)
            iterator = iter(instance)
            chunk1 = six.next(iterator)
            self.assertEqual(b"a" * mebibyte, chunk1.read(mebibyte))
            chunk2 = six.next(iterator)
            self.assertEqual(b"b", chunk2.read(mebibyte))

    def test_split_file_irregular_size_2(self):
        with tempfile.TemporaryFile() as f:
            f.write(b"a" * mebibyte)
            f.write(b"b" * (mebibyte - 1))
            f.flush()
            f.seek(0)
            instance = SplitStream(f, mebibyte)
            self.assertEqual(len(instance), 2)
            iterator = iter(instance)
            chunk1 = six.next(iterator)
            self.assertEqual(b"a" * mebibyte, chunk1.read(mebibyte))
            chunk2 = six.next(iterator)
            self.assertEqual(b"b" * (mebibyte - 1), chunk2.read(mebibyte))

    def test_split_url(self):
        with tempfile.NamedTemporaryFile() as f:
            f.write(b"a" * mebibyte)
            f.write(b"b" * mebibyte)
            f.flush()
            with closing(urlopen(path2url(f.name))) as stream:
                instance = SplitStream(stream, mebibyte)
                self.assertEqual(len(instance), 2)
                for m, c in izip(instance, [b"a", b"b"]):
                    self.assertEqual(m.read(mebibyte), c * mebibyte)

    def test_split_url_irregular_size(self):
        with tempfile.NamedTemporaryFile() as f:
            f.write(b"a" * mebibyte)
            f.write(b"b")
            f.flush()
            with closing(urlopen(path2url(f.name))) as stream:
                instance = SplitStream(stream, mebibyte)
                self.assertEqual(len(instance), 2)
                iterator = iter(instance)
                chunk1 = six.next(iterator)
                self.assertEqual(b"a" * mebibyte, chunk1.read(mebibyte))
                chunk2 = six.next(iterator)
                self.assertEqual(b"b", chunk2.read(mebibyte))

    def test_split_url_irregular_size_2(self):
        with tempfile.NamedTemporaryFile() as f:
            f.write(b"a" * mebibyte)
            f.write(b"b" * (mebibyte - 1))
            f.flush()
            with closing(urlopen(path2url(f.name))) as stream:
                instance = SplitStream(stream, mebibyte)
                self.assertEqual(len(instance), 2)
                iterator = iter(instance)
                chunk1 = six.next(iterator)
                self.assertEqual(b"a" * mebibyte, chunk1.read(mebibyte))
                chunk2 = six.next(iterator)
                self.assertEqual(b"b" * (mebibyte - 1), chunk2.read(mebibyte))

    def test_split_bytes(self):
        instance = SplitStream(b"a" * small_chunk + b"b" * small_chunk,
                               small_chunk)
        self.assertEqual(len(instance), 2)
        for m, c in izip(instance, [b"a", b"b"]):
            self.assertEqual(c * small_chunk, m.read(small_chunk))

    def test_split_bytes_irregular_size(self):
        instance = SplitStream(b"a" * small_chunk + b"b", small_chunk)
        self.assertEqual(len(instance), 2)
        iterator = iter(instance)
        chunk1 = six.next(iterator)
        self.assertEqual(b"a" * small_chunk, chunk1.read(small_chunk))
        chunk2 = six.next(iterator)
        self.assertEqual(b"b", chunk2.read(small_chunk))

    def test_split_bytes_irregular_size_2(self):
        instance = SplitStream(b"a" * small_chunk + b"b" * (small_chunk - 1),
                               small_chunk)
        self.assertEqual(len(instance), 2)
        iterator = iter(instance)
        chunk1 = six.next(iterator)
        self.assertEqual(b"a" * small_chunk, chunk1.read(small_chunk))
        chunk2 = six.next(iterator)
        self.assertEqual(b"b" * (small_chunk - 1), chunk2.read(small_chunk))

    def test_split_combine_stream_misaligned_with_chunk_size_1(self):
        instance = SplitStream(dict(
            Body=CombineStreams([io.BytesIO(b"1234"), io.BytesIO(b"567890123456789")]),
            ContentLength=19
        ), 5)
        self.assertEqual(len(instance), 4)
        iterator = iter(instance)
        chunk1 = six.next(iterator)
        self.assertEqual(b"12345", chunk1.read(5))
        chunk2 = six.next(iterator)
        self.assertEqual(b"67890", chunk2.read(5))
        chunk3 = six.next(iterator)
        self.assertEqual(b"12345", chunk3.read(5))
        chunk4 = six.next(iterator)
        self.assertEqual(b"6789", chunk4.read(5))

    def test_split_combine_stream_misaligned_with_chunk_size_2(self):
        instance = SplitStream(dict(
            Body=CombineStreams([io.BytesIO(b"123456789"), io.BytesIO(b"012345678")]),
            ContentLength=18
        ), 5)
        self.assertEqual(len(instance), 4)
        iterator = iter(instance)
        chunk1 = six.next(iterator)
        self.assertEqual(b"12345", chunk1.read(5))
        chunk2 = six.next(iterator)
        self.assertEqual(b"67890", chunk2.read(5))
        chunk3 = six.next(iterator)
        self.assertEqual(b"12345", chunk3.read(5))
        chunk4 = six.next(iterator)
        self.assertEqual(b"678", chunk4.read(5))

    def test_split_combine_stream_misaligned_with_chunk_size_3(self):
        instance = SplitStream(dict(
            Body=CombineStreams([io.BytesIO(b"123"), io.BytesIO(b"456"), io.BytesIO(b"789"), io.BytesIO(b"012")]),
            ContentLength=12
        ), 5)
        self.assertEqual(len(instance), 3)
        iterator = iter(instance)
        chunk1 = six.next(iterator)
        self.assertEqual(b"12345", chunk1.read(5))
        chunk2 = six.next(iterator)
        self.assertEqual(b"67890", chunk2.read(5))
        chunk3 = six.next(iterator)
        self.assertEqual(b"12", chunk3.read(5))

    def test_combine_streams(self):
        instance = CombineStreams(io.BytesIO(b"Hello") for i in range(20))
        result = b""
        for i in range(1000):
            read_result = instance.read(i)
            result += read_result
            if len(read_result) < i:
                break

        self.assertEqual(instance.read(10), b"")
        self.assertEqual(instance.read(), b"")
        self.assertEqual(result, b"Hello" * 20)

    def test_combine_streams_readall(self):
        instance = CombineStreams(io.BytesIO(b"Hello") for i in range(20))
        result = instance.read()

        self.assertEqual(instance.read(10), b"")
        self.assertEqual(instance.read(), b"")
        self.assertEqual(result, b"Hello" * 20)

    def test_iterator_mixin(self):
        # import pudb
        # pu.db
        instance = FakeMixinUser(MIXIN_DATA, 4)
        self.assertEqual(b'a\n', instance.readline())
        self.assertEqual(b'aa\n', instance.readline())
        self.assertEqual(b'aaa\n', instance.readline())
        self.assertEqual(b'aaaa\n', instance.readline())
        self.assertEqual(b'aaaaa\n', instance.readline())
        self.assertEqual(b'aaaaaa\n', instance.readline())
        self.assertEqual(b'', instance.readline())

    def test_iterator_mixin_list(self):
        # import pudb
        # pu.db
        instance = FakeMixinUser(MIXIN_DATA, 4)
        self.assertEqual([
            b'a\n',
            b'aa\n',
            b'aaa\n',
            b'aaaa\n',
            b'aaaaa\n',
            b'aaaaaa\n',
        ], instance.readlines())


if __name__ == '__main__':
    main()
