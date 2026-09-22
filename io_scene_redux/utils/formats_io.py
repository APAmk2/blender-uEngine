import struct


class FormatError(ValueError):
    pass


class PackedReader:
    str_end = 0
    FILE = None

    def __init__(self, data):
        self.offs = 0
        self.data = memoryview(data)

    @property
    def pos(self):
        return self.offs

    @pos.setter
    def pos(self, value):
        self.offs = value

    def read(self, count):
        if count < 0 or self.offs + count > len(self.data):
            raise FormatError('Truncated record at offset {}'.format(self.offs))
        value = self.data[self.offs:self.offs + count]
        self.offs += count
        return value

    def getf(self, fmt):
        return struct.unpack(fmt, self.read(struct.calcsize(fmt)))

    def unpack(self, fmt):
        return self.getf(fmt)

    def gets(self):
        zero_pos = self.data[self.offs:].tobytes().find(bytes((self.str_end,)))
        if zero_pos < 0:
            raise FormatError('Unterminated string at offset {}'.format(self.offs))
        value = self.read(zero_pos + 1)[:-1].tobytes()
        return value.decode('utf-8', 'surrogateescape')

    def stringz(self):
        return self.gets()

    def readed(self):
        if self.offs != len(self.data):
            raise FormatError('Unexpected {} trailing bytes'.format(
                len(self.data) - self.offs
            ))

    def done(self):
        self.readed()

    def is_end(self):
        return self.offs >= len(self.data)


class ChunkedReader:
    def __init__(self, data):
        self.offs = 0
        self.data = memoryview(data)

    def __iter__(self):
        return self

    def __next__(self):
        if self.offs == len(self.data):
            raise StopIteration
        if self.offs + 8 > len(self.data):
            raise FormatError('Truncated record at offset {}'.format(self.offs))
        chunk_id, chunk_size = struct.unpack_from('<2I', self.data, self.offs)
        self.offs += 8
        if self.offs + chunk_size > len(self.data):
            raise FormatError('Truncated record at offset {}'.format(self.offs))
        chunk_data = self.data[self.offs:self.offs + chunk_size].tobytes()
        self.offs += chunk_size
        return chunk_id, chunk_data

    def read(self):
        return list(self)

    def get_chunk(self, expected_id):
        previous = self.offs
        try:
            for chunk_id, chunk_data in self:
                if chunk_id == expected_id:
                    return chunk_data
        finally:
            self.offs = previous
        return None


class PackedWriter:
    def __init__(self):
        self.data = bytearray()

    def putf(self, fmt, *values):
        self.data += struct.pack(fmt, *values)

    def puts(self, value):
        self.data += value.encode('utf-8', 'surrogateescape') + b'\0'

    def putb(self, payload):
        self.data += payload


class ChunkedWriter(PackedWriter):
    def put(self, chunk_id, payload):
        if isinstance(payload, PackedWriter):
            payload = payload.data
        self.putf('<2I', chunk_id, len(payload))
        self.putb(payload)


def pack_chunk(chunk_id, payload):
    writer = ChunkedWriter()
    writer.put(chunk_id, payload)
    return bytes(writer.data)


def stringz(value):
    writer = PackedWriter()
    writer.puts(value)
    return bytes(writer.data)


Reader = PackedReader
