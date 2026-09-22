from dataclasses import dataclass, field
import struct
import math
from .common import (FormatError, Reader, chunks, one, header, bounds_header,
                     Material, _material, _material_bytes, pack_chunk)

@dataclass
class StaticPart:
    material: Material
    vertices: list  # (position3, normal3, uv2, packed_color)
    faces: list
    extra: list = field(default_factory=list)
    vertex_basis: list = field(default_factory=list)  # Versions 16/18/21 tangent/binormal pairs.

@dataclass
class StaticModel:
    parts: list
    header: bytes = b""
    guid: bytes = bytes(16)
    extra: list = field(default_factory=list)

def read_static(data, expected_type=10, versions=None):
    top = chunks(data)
    h = one(top, 1)
    if len(h) not in (64, 80):
        raise FormatError("Static header must be 64 or 80 bytes")
    if versions is None:
        versions = ((7, 17, 20, 21, 22, 23) if expected_type == 1 else
                    (8, 16, 18, 21, 22, 23))
    header(h[:64], expected_type, versions=versions)
    version = h[0]
    parts = []
    for number, part_data in chunks(one(top, 9)):
        if number != len(parts):
            raise FormatError("Static part IDs must be sequential")
        part = chunks(part_data)
        material = (_material(one(part, 2), False, 0, 3)
                    if expected_type == 1 and version == 7 else
                    _material(one(part, 2), False, 4) if expected_type == 1 else
                    _material(one(part, 2), True, 2, 3) if version == 8 else
                    _material(one(part, 2), True, 1 if version in (16, 18) else 2))
        r = Reader(one(part, 3))
        vertex_format = r.unpack("<I")[0] if expected_type == 1 else None
        if expected_type == 1 and vertex_format != 2:
            raise FormatError("Unsupported static .model vertex format %d" % vertex_format)
        count = r.unpack("<I")[0]
        stride = (32 if expected_type == 1 else
                  56 if version in (8, 16) else 57 if version in (18, 21) else 36)
        if len(r.data) != (8 if expected_type == 1 else 4) + count * stride:
            raise FormatError("Invalid static vertex count")
        vertices = []
        vertex_basis = []
        for _ in range(count):
            if expected_type == 1:
                v = r.unpack("<3f3I2f")
                packed = v[3]
                signed = tuple(((packed >> shift) & 255) - 256
                               if (packed >> shift) & 128 else (packed >> shift) & 255
                               for shift in (0, 8, 16))
                normal = tuple(value / 127.0 for value in signed)
                length = math.sqrt(sum(value * value for value in normal)) or 1.0
                vertices.append((v[:3], tuple(value / length for value in normal),
                                 v[6:8], v[5]))
            elif version in (8, 16):
                v = r.unpack("<3f3f3f3f2f")
                vertices.append((v[:3], v[3:6], v[12:14], 0xffffffff))
                vertex_basis.append((v[6:9], v[9:12]))
            elif version in (18, 21):
                v = r.unpack("<3f3f3f3f2fB")
                vertices.append((v[:3], v[3:6], v[12:14], v[14] * 0x01010101))
                vertex_basis.append((v[6:9], v[9:12]))
            else:
                v = r.unpack("<3f3f2fI")
                vertices.append((v[:3], v[3:6], v[6:8], v[8]))
        r = Reader(one(part, 4))
        count = r.unpack("<I")[0]
        if expected_type == 1:
            if count % 3 or len(r.data) != 4 + count * 2:
                raise FormatError("Invalid static .model index count")
            indices = r.unpack("<%dH" % count)
            faces = [indices[index:index + 3] for index in range(0, count, 3)]
        else:
            if len(r.data) != 4 + count * 12:
                raise FormatError("Invalid static face count")
            faces = [r.unpack("<III") for _ in range(count)]
        if any(i >= len(vertices) for face in faces for i in face):
            raise FormatError("Static face index out of range")
        parts.append(StaticPart(material, vertices, faces,
                                [(i, p) for i, p in part if i not in (2, 3, 4)],
                                vertex_basis))
    return StaticModel(parts, h[:64], h[64:],
                       [(i, p) for i, p in top if i not in (1, 9)])

def write_static(model):
    part_bytes = []
    all_positions = []
    version = model.header[0] if model.header else 22
    if version not in (8, 16, 18, 21, 22, 23):
        raise FormatError("Unsupported static version %d" % version)
    for part in model.parts:
        if any(i >= len(part.vertices) or i < 0 for face in part.faces for i in face):
            raise FormatError("Static face index out of range")
        all_positions += [v[0] for v in part.vertices]
        vertices = struct.pack("<I", len(part.vertices))
        for index, (p, n, uv, color) in enumerate(part.vertices):
            if version in (8, 16, 18, 21):
                if index < len(part.vertex_basis) and part.vertex_basis[index] is not None:
                    tangent, binormal = part.vertex_basis[index]
                else:
                    # New vertices need a valid orthogonal basis for the legacy record.
                    tangent = (0.0, 0.0, 1.0) if abs(n[1]) > 0.9 else (0.0, 1.0, 0.0)
                    dot = sum(a * b for a, b in zip(tangent, n))
                    tangent = tuple(a - dot * b for a, b in zip(tangent, n))
                    binormal = (n[1]*tangent[2]-n[2]*tangent[1],
                                n[2]*tangent[0]-n[0]*tangent[2],
                                n[0]*tangent[1]-n[1]*tangent[0])
                vertices += struct.pack("<3f3f3f3f2f", *p, *n, *tangent,
                                        *binormal, *uv)
                if version not in (8, 16):
                    vertices += struct.pack("<B", color & 0xff)
            else:
                vertices += struct.pack("<3f3f2fI", *p, *n, *uv, color)
        faces = struct.pack("<I", len(part.faces))
        faces += b"".join(struct.pack("<III", *face) for face in part.faces)
        payload = pack_chunk(2, _material_bytes(
            part.material, True, 2 if version == 8 else 1 if version in (16, 18) else 2,
            3 if version == 8 else 4))
        payload += pack_chunk(3, vertices) + pack_chunk(4, faces)
        payload += b"".join(pack_chunk(i, p) for i, p in part.extra)
        part_bytes.append(pack_chunk(len(part_bytes), payload))
    h = model.header or bounds_header(all_positions, 10)
    if len(model.guid) not in (0, 16):
        raise FormatError("GUID must be absent or 16 bytes")
    return (pack_chunk(9, b"".join(part_bytes)) + pack_chunk(1, h + model.guid)
            + b"".join(pack_chunk(i, p) for i, p in model.extra))

