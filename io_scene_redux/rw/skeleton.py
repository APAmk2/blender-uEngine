from dataclasses import dataclass, field
import struct
from .common import FormatError, Reader, chunks, one, pack_chunk, stringz

@dataclass
class Bone:
    name: str
    parent: str
    q: tuple  # Redux order x,y,z,w
    t: tuple
    body_part: int = 0

@dataclass
class Locator:
    name: str
    parent: str
    q: tuple
    t: tuple
    flags: int = 0

@dataclass
class Skeleton:
    bones: list
    crc: int
    locators: list = field(default_factory=list)
    partitions: list = field(default_factory=list)
    params: list = field(default_factory=list)
    motions: str = ""
    version: int = 4
    extra: list = field(default_factory=list)
    chunk_order: list = field(default_factory=list)

def read_skeleton(data):
    top = chunks(data)
    version = struct.unpack("<I", one(top, 1))[0]
    if version not in (1, 4):
        raise FormatError("Unsupported compact skeleton version %d" % version)
    r = Reader(one(top, 13))
    crc, count = r.unpack("<IH")
    bones = []
    for _ in range(count):
        name, parent = r.stringz(), r.stringz()
        if version == 4:
            q = r.unpack("<4f")
        else:
            # Version 1 stores Euler angles. Keep them for Blender conversion.
            q = r.unpack("<3f")
        t = r.unpack("<3f")
        bp = r.unpack("<H")[0]
        bones.append(Bone(name, parent, q, t, bp))
    r.done()
    locators = []
    if any(i == 14 for i, _ in top):
        r = Reader(one(top, 14))
        for _ in range(r.unpack("<H")[0]):
            locators.append(Locator(r.stringz(), r.stringz(), r.unpack("<4f"),
                                    r.unpack("<3f"), r.unpack("<B")[0]))
        r.done()
    partitions = []
    if any(i == 17 for i, _ in top):
        r = Reader(one(top, 17))
        for _ in range(r.unpack("<H")[0]):
            partitions.append((r.stringz(), r.read(count).tobytes()))
        r.done()
    params = []
    if any(i == 27 for i, _ in top):
        r = Reader(one(top, 27))
        for _ in range(r.unpack("<H")[0]):
            params.append((r.stringz(), *r.unpack("<3f")))
        r.done()
    motions = Reader(one(top, 19)).stringz() if any(i == 19 for i, _ in top) else ""
    return Skeleton(bones, crc, locators, partitions, params, motions, version,
                    [(i, p) for i, p in top if i not in (1, 13, 14, 17, 19, 27)],
                    [i for i, _ in top])

def write_skeleton(skeleton):
    if skeleton.version != 4:
        raise FormatError("Only version 4 compact skeleton export is supported")
    if len(skeleton.bones) > 65535:
        raise FormatError("Too many bones")
    bones = struct.pack("<IH", skeleton.crc, len(skeleton.bones))
    for bone in skeleton.bones:
        bones += stringz(bone.name) + stringz(bone.parent)
        bones += struct.pack("<4f3fH", *bone.q, *bone.t, bone.body_part)
    locators = struct.pack("<H", len(skeleton.locators))
    for loc in skeleton.locators:
        locators += stringz(loc.name) + stringz(loc.parent)
        locators += struct.pack("<4f3fB", *loc.q, *loc.t, loc.flags)
    partitions = struct.pack("<H", len(skeleton.partitions))
    for name, influence in skeleton.partitions:
        if len(influence) != len(skeleton.bones):
            raise FormatError("Partition length differs from bone count")
        partitions += stringz(name) + influence
    params = struct.pack("<H", len(skeleton.params))
    for name, b, e, loop in skeleton.params:
        params += stringz(name) + struct.pack("<3f", b, e, loop)
    payloads = {1: struct.pack("<I", 4), 13: bones, 14: locators,
                17: partitions, 27: params}
    if skeleton.motions:
        payloads[19] = stringz(skeleton.motions)
    payloads.update(skeleton.extra)
    order = list(skeleton.chunk_order or [1, 13, 14, 17, 19, 26, 27])
    order += [i for i in payloads if i not in order]
    return b"".join(pack_chunk(i, payloads[i]) for i in order if i in payloads)

