from __future__ import absolute_import, print_function

import gzip
import io
import tempfile
from contextlib import closing
from urllib.parse import urljoin
from urllib.request import pathname2url, urlopen

from mesh_client.io_helpers import (
    CombineStreams,
    GzipCompressStream,
    GzipDecompressStream,
    IteratorMixin,
    SplitStream,
)


def path2url(path):
    return urljoin("file:", pathname2url(path))


try:
    from itertools import izip  # type: ignore[attr-defined]
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


def test_gzip_compress_stream():
    underlying = io.BytesIO(b"This is a short test stream")
    instance = GzipCompressStream(underlying, block_size=4)
    result = b""
    for i in range(1000):
        read_result = instance.read(i)
        result += read_result
        if len(read_result) < i:
            break
    assert instance.read(10) == b""
    assert instance.read() == b""

    # Decode with GzipFile
    test_decoder = gzip.GzipFile("", mode="r", fileobj=io.BytesIO(result))
    assert test_decoder.read() == b"This is a short test stream"


def test_gzip_compress_stream_read_all():
    underlying = io.BytesIO(b"This is a short test stream")
    instance = GzipCompressStream(underlying, block_size=4)
    result = instance.read()
    assert instance.read(10) == b""
    assert instance.read() == b""

    # Decode with GzipFile
    test_decoder = gzip.GzipFile("", mode="r", fileobj=io.BytesIO(result))
    assert test_decoder.read() == b"This is a short test stream"


def test_gzip_decompress_stream():
    underlying = io.BytesIO()
    gzwriter = gzip.GzipFile(fileobj=underlying, mode="w")
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
    assert instance.read(10) == b""
    assert instance.read() == b""

    assert result == b"This is a short test stream"


def test_gzip_decompress_stream_read_all():
    underlying = io.BytesIO()
    gzwriter = gzip.GzipFile(fileobj=underlying, mode="w")
    gzwriter.write(b"This is a short test stream")
    gzwriter.close()
    underlying.seek(0)

    instance = GzipDecompressStream(underlying, block_size=4)
    result = instance.read()
    assert instance.read(10) == b""
    assert instance.read() == b""

    assert result == b"This is a short test stream"


def test_split_file():
    with tempfile.TemporaryFile() as f:
        f.write(b"a" * mebibyte)
        f.write(b"b" * mebibyte)
        f.flush()
        f.seek(0)
        instance = SplitStream(f, mebibyte)
        assert len(instance) == 2
        for m, c in izip(instance, [b"a", b"b"]):
            assert m.read(mebibyte) == c * mebibyte


def test_split_file_irregular_size():
    with tempfile.TemporaryFile() as f:
        f.write(b"a" * mebibyte)
        f.write(b"b")
        f.flush()
        f.seek(0)
        instance = SplitStream(f, mebibyte)
        assert len(instance) == 2
        iterator = iter(instance)
        chunk1 = next(iterator)
        assert chunk1.read(mebibyte) == b"a" * mebibyte
        chunk2 = next(iterator)
        assert chunk2.read(mebibyte) == b"b"


def test_split_file_irregular_size_2():
    with tempfile.TemporaryFile() as f:
        f.write(b"a" * mebibyte)
        f.write(b"b" * (mebibyte - 1))
        f.flush()
        f.seek(0)
        instance = SplitStream(f, mebibyte)
        assert len(instance) == 2
        iterator = iter(instance)
        chunk1 = next(iterator)
        assert chunk1.read(mebibyte) == b"a" * mebibyte
        chunk2 = next(iterator)
        assert chunk2.read(mebibyte) == b"b" * (mebibyte - 1)


def test_split_url():
    with tempfile.NamedTemporaryFile() as f:
        f.write(b"a" * mebibyte)
        f.write(b"b" * mebibyte)
        f.flush()
        with closing(urlopen(path2url(f.name))) as stream:
            instance = SplitStream(stream, mebibyte)
            assert len(instance) == 2
            for m, c in izip(instance, [b"a", b"b"]):
                assert m.read(mebibyte) == c * mebibyte


def test_split_url_irregular_size():
    with tempfile.NamedTemporaryFile() as f:
        f.write(b"a" * mebibyte)
        f.write(b"b")
        f.flush()
        with closing(urlopen(path2url(f.name))) as stream:
            instance = SplitStream(stream, mebibyte)
            assert len(instance) == 2
            iterator = iter(instance)
            chunk1 = next(iterator)
            assert chunk1.read(mebibyte) == b"a" * mebibyte
            chunk2 = next(iterator)
            assert chunk2.read(mebibyte) == b"b"


def test_split_url_irregular_size_2():
    with tempfile.NamedTemporaryFile() as f:
        f.write(b"a" * mebibyte)
        f.write(b"b" * (mebibyte - 1))
        f.flush()
        with closing(urlopen(path2url(f.name))) as stream:
            instance = SplitStream(stream, mebibyte)
            assert len(instance) == 2
            iterator = iter(instance)
            chunk1 = next(iterator)
            assert chunk1.read(mebibyte) == b"a" * mebibyte
            chunk2 = next(iterator)
            assert chunk2.read(mebibyte) == b"b" * (mebibyte - 1)


def test_split_bytes():
    instance = SplitStream(b"a" * small_chunk + b"b" * small_chunk, small_chunk)
    assert len(instance) == 2
    for m, c in izip(instance, [b"a", b"b"]):
        assert m.read(small_chunk) == c * small_chunk


def test_split_bytes_irregular_size():
    instance = SplitStream(b"a" * small_chunk + b"b", small_chunk)
    assert len(instance) == 2
    iterator = iter(instance)
    chunk1 = next(iterator)
    assert chunk1.read(small_chunk) == b"a" * small_chunk
    chunk2 = next(iterator)
    assert chunk2.read(small_chunk) == b"b"


def test_split_bytes_irregular_size_2():
    instance = SplitStream(b"a" * small_chunk + b"b" * (small_chunk - 1), small_chunk)
    assert len(instance) == 2
    iterator = iter(instance)
    chunk1 = next(iterator)
    assert chunk1.read(small_chunk) == b"a" * small_chunk
    chunk2 = next(iterator)
    assert chunk2.read(small_chunk) == b"b" * (small_chunk - 1)


def test_split_combine_stream_misaligned_with_chunk_size_1():
    instance = SplitStream(
        dict(Body=CombineStreams([io.BytesIO(b"1234"), io.BytesIO(b"567890123456789")]), ContentLength=19), 5
    )
    assert len(instance) == 4
    iterator = iter(instance)
    chunk1 = next(iterator)
    assert chunk1.read(5) == b"12345"
    chunk2 = next(iterator)
    assert chunk2.read(5) == b"67890"
    chunk3 = next(iterator)
    assert chunk3.read(5) == b"12345"
    chunk4 = next(iterator)
    assert chunk4.read(5) == b"6789"


def test_split_combine_stream_misaligned_with_chunk_size_2():
    instance = SplitStream(
        dict(Body=CombineStreams([io.BytesIO(b"123456789"), io.BytesIO(b"012345678")]), ContentLength=18), 5
    )
    assert len(instance) == 4
    iterator = iter(instance)
    chunk1 = next(iterator)
    assert chunk1.read(5) == b"12345"
    chunk2 = next(iterator)
    assert chunk2.read(5) == b"67890"
    chunk3 = next(iterator)
    assert chunk3.read(5) == b"12345"
    chunk4 = next(iterator)
    assert chunk4.read(5) == b"678"


def test_split_combine_stream_misaligned_with_chunk_size_3():
    instance = SplitStream(
        dict(
            Body=CombineStreams([io.BytesIO(b"123"), io.BytesIO(b"456"), io.BytesIO(b"789"), io.BytesIO(b"012")]),
            ContentLength=12,
        ),
        5,
    )
    assert len(instance) == 3
    iterator = iter(instance)
    chunk1 = next(iterator)
    assert chunk1.read(5) == b"12345"
    chunk2 = next(iterator)
    assert chunk2.read(5) == b"67890"
    chunk3 = next(iterator)
    assert chunk3.read(5) == b"12"


def test_combine_streams():
    instance = CombineStreams(io.BytesIO(b"Hello") for i in range(20))
    result = b""
    for i in range(1000):
        read_result = instance.read(i)
        result += read_result
        if len(read_result) < i:
            break

    assert instance.read(10) == b""
    assert instance.read() == b""
    assert result == b"Hello" * 20


def test_combine_streams_readall():
    instance = CombineStreams(io.BytesIO(b"Hello") for i in range(20))
    result = instance.read()

    assert instance.read(10) == b""
    assert instance.read() == b""
    assert result == b"Hello" * 20


def test_iterator_mixin():
    # import pudb
    # pu.db
    instance = FakeMixinUser(MIXIN_DATA, 4)
    assert instance.readline() == b"a\n"
    assert instance.readline() == b"aa\n"
    assert instance.readline() == b"aaa\n"
    assert instance.readline() == b"aaaa\n"
    assert instance.readline() == b"aaaaa\n"
    assert instance.readline() == b"aaaaaa\n"
    assert instance.readline() == b""


def test_iterator_mixin_list():
    # import pudb
    # pu.db
    instance = FakeMixinUser(MIXIN_DATA, 4)
    assert instance.readlines() == [
        b"a\n",
        b"aa\n",
        b"aaa\n",
        b"aaaa\n",
        b"aaaaa\n",
        b"aaaaaa\n",
    ]
