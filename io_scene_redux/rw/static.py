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
    shadow_faces: list = field(default_factory=list)
    auxiliary: bytes = b""
    material_tail: bytes = b""
    lods: list = field(default_factory=list)
    selected_lod: int = -1

@dataclass
class StaticModel:
    parts: list
    header: bytes = b""
    guid: bytes = bytes(16)
    extra: list = field(default_factory=list)


@dataclass
class LodDescriptor:
    ident: int
    offset: int
    vertex_count: int
    face_count: int
    shadow_face_count: int
    neighbourhood: bool


def _lod_descriptors(data):
    reader = Reader(data)
    count = reader.unpack("<I")[0]
    result = []
    for _index in range(count):
        values = reader.unpack("<B4IB")
        result.append(LodDescriptor(values[0], *values[1:5], bool(values[5])))
    reader.done()
    return result


def _normal(value):
    raw = ((value >> 16) & 255, (value >> 8) & 255, value & 255)
    result = tuple(component / 127.5 - 1.0 for component in raw)
    length = math.sqrt(sum(component * component for component in result)) or 1.0
    return tuple(component / length for component in result)


def _modern_vertex(data, scale):
    values = struct.unpack("<8I", data)
    xbits, ybits, zbits = values[0], values[1], values[2]
    qx = xbits & 0x7ffffff
    qy = (xbits >> 27) | ((ybits & 0x1fffff) << 5)
    qz = (ybits >> 21) | ((zbits & 0xffff) << 11)
    position = (qx * scale / (1 << 26) - scale,
                qy * scale / (1 << 25) - scale,
                qz * scale / (1 << 26) - scale)
    u_hi, v_hi = struct.unpack_from("<2h", data, 12)
    uv = (u_hi / 2048.0 + data[10] / 522240.0,
          v_hi / 2048.0 + data[11] / 522240.0)
    return position, _normal(values[5]), uv, values[7] & 0xffffff


def _modern_geometry(raw, descriptor, scale):
    reader = Reader(raw)
    if descriptor.offset > len(raw):
        raise FormatError("Static LOD geometry offset is outside chunk 47")
    reader.pos = descriptor.offset
    vertices = [_modern_vertex(reader.read(32).tobytes(), scale)
                for _index in range(descriptor.vertex_count)]
    faces = [reader.unpack("<3H") for _index in range(descriptor.face_count)]
    shadow = [reader.unpack("<3H") for _index in range(descriptor.shadow_face_count)]
    if any(index >= descriptor.vertex_count
           for face in faces + shadow for index in face):
        raise FormatError("Static LOD face index out of range")
    return vertices, faces, shadow


def _modern_material(data):
    reader = Reader(data)
    values = [reader.stringz() for _index in range(4)]
    flags = reader.unpack("<H")[0]
    tail = reader.read(len(reader.data) - reader.pos).tobytes()
    return Material(*values, flags=flags), tail

def read_static(data, expected_type=10, versions=None):
    top = chunks(data)
    h = one(top, 1)
    if len(h) not in (64, 80):
        raise FormatError("Static header must be 64 or 80 bytes")
    if versions is None:
        versions = (((7,) + tuple(range(11, 56))) if expected_type == 1 else
                    (8, 16, 18, 21, 22, 23))
    header(h[:64], expected_type, versions=versions)
    version = h[0]
    parts = []
    for number, part_data in chunks(one(top, 9)):
        if number != len(parts):
            raise FormatError("Static part IDs must be sequential")
        part = chunks(part_data)
        material_tail = b""
        if expected_type == 1 and version == 7:
            material = _material(one(part, 2), False, 0, 3)
        elif expected_type == 1 and version >= 24:
            material, material_tail = _modern_material(one(part, 2))
        elif expected_type == 1:
            material = _material(one(part, 2), False, 4)
        elif version == 8:
            material = _material(one(part, 2), True, 2, 3)
        else:
            material = _material(one(part, 2), True, 1 if version in (16, 18) else 2)
        vertices = []
        vertex_basis = []
        shadow_faces = []
        auxiliary = b""
        lods = []
        selected_lod = -1
        if expected_type == 1 and version >= 55:
            lods = _lod_descriptors(one(part, 45))
            valid = [item for item in lods if item.vertex_count and item.face_count]
            if not valid:
                raise FormatError("Static model part has no valid LOD")
            selected = max(valid, key=lambda item: item.ident)
            selected_lod = selected.ident
            scale = struct.unpack_from("<f", one(part, 1), 56)[0]
            vertices, faces, shadow_faces = _modern_geometry(one(top, 47), selected, scale)
        else:
            r = Reader(one(part, 3))
            vertex_format = r.unpack("<I")[0] if expected_type == 1 else None
            if expected_type == 1 and vertex_format != 2:
                raise FormatError("Unsupported static .model vertex format %d" % vertex_format)
            count = r.unpack("<I")[0]
            auxiliary_count = (r.unpack("<H")[0]
                               if expected_type == 1 and 30 <= version <= 51 else 0)
            stride = (32 if expected_type == 1 else
                      56 if version in (8, 16) else 57 if version in (18, 21) else 36)
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
            auxiliary = r.read(auxiliary_count * 16).tobytes()
            r.done()
            r = Reader(one(part, 4))
            count = r.unpack("<I")[0]
            if expected_type == 1 and version >= 30:
                shadow_count = r.unpack("<H")[0]
                faces = [r.unpack("<3H") for _ in range(count)]
                shadow_faces = [r.unpack("<3H") for _ in range(shadow_count)]
                r.done()
            elif expected_type == 1:
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
                                [(i, p) for i, p in part if i not in (2, 3, 4, 45)],
                                vertex_basis, shadow_faces, auxiliary, material_tail,
                                lods, selected_lod))
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

