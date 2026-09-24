from dataclasses import dataclass, field
import struct
from .common import (FormatError, Reader, chunks, one, header, bounds_header,
                     Material, _material, _material_bytes, pack_chunk)

@dataclass
class SkinVertex:
    offset: tuple
    normal: int
    tangent: int
    binormal: int
    bones: int
    weights: int
    uv: tuple
    modern: bool = False
    direct_bones: bool = False

    def influences(self, used_bones):
        result = []
        legacy_count = 1 <= self.offset[3] <= 4
        # The shader swizzles packed COLOR bytes .zyxw for both IDs and weights.
        slots = ((2, 1, 0, 3) if self.modern or not legacy_count else
                 (2, 1, 0, 3)[:self.offset[3]])
        for slot in slots:
            idx = (self.bones >> (slot * 8)) & 255
            weight = (self.weights >> (slot * 8)) & 255
            used_index = idx if self.direct_bones else idx // 3
            if ((not self.direct_bones and idx % 3) or
                    used_index >= len(used_bones)):
                raise FormatError("Invalid packed bone index")
            if weight:
                result.append((used_bones[used_index], weight / 255))
        return result

    def texcoord(self):
        if not self.modern:
            return self.uv[0] / 2048, self.uv[1] / 2048
        # Version 55 uses spare packed tangent bits as the low UV bits.
        low_u = (self.tangent & 0xff) & 0x0f
        low_v = (self.tangent >> 4) & 0xff
        return ((self.uv[0] + low_u / 16.0) / 2048,
                (self.uv[1] + low_v / 16.0) / 2048)


@dataclass
class LodDescriptor:
    ident: int
    offset: int
    vertex_count: int
    face_count: int
    shadow_face_count: int
    neighbourhood: bool

@dataclass
class SkinPart:
    material: Material
    used_bones: list
    bone_boxes: bytes
    vertices: list
    faces: list
    shadow_faces: list
    header: bytes = b""
    extra: list = field(default_factory=list)
    scale: float = 12.0
    auxiliary: bytes = b""
    lods: list = field(default_factory=list)
    selected_lod: int = -1

@dataclass
class SkinModel:
    parts: list
    bones_crc: int
    header: bytes = b""
    extra: list = field(default_factory=list)


def _part_scale(raw_header):
    version = raw_header[0]
    if version < 29:
        return 12.0
    if version < 31:
        bounds = struct.unpack_from("<6f", raw_header, 4)
        return max(abs(value) for value in bounds)
    return struct.unpack_from("<f", raw_header, 56)[0]


def _lod_descriptors(data):
    reader = Reader(data)
    count = reader.unpack("<I")[0]
    result = []
    for _index in range(count):
        values = reader.unpack("<B4IB")
        result.append(LodDescriptor(values[0], *values[1:5], bool(values[5])))
    reader.done()
    return result


def _lod_geometry(raw, descriptor, modern=True, direct_bones=True):
    if descriptor.offset > len(raw):
        raise FormatError("Skin LOD geometry offset is outside chunk 47")
    reader = Reader(raw)
    reader.pos = descriptor.offset
    vertices = []
    for _index in range(descriptor.vertex_count):
        a = reader.unpack("<4h5I2h")
        vertices.append(SkinVertex(a[:4], *a[4:9], a[9:11], modern,
                                   direct_bones))
    faces = [reader.unpack("<3H") for _index in range(descriptor.face_count)]
    shadow = [reader.unpack("<3H") for _index in range(descriptor.shadow_face_count)]
    if any(index >= descriptor.vertex_count
           for face in faces + shadow for index in face):
        raise FormatError("Skin LOD face index out of range")
    return vertices, faces, shadow

def read_mesh(data, geometry_data=None):
    top = chunks(data)
    raw_header = one(top, 1)
    if raw_header[:2] == bytes((16, 0)):
        h = header(raw_header, 0, (16,))
        crc = struct.unpack("<I", one(top, 13))[0]
        if one(top, 9):
            raise FormatError("Empty skin placeholder contains parts")
        return SkinModel([], crc, h,
                         [(i, p) for i, p in top if i not in (1, 9, 13)])
    version = raw_header[0] if raw_header else -1
    versions = (7, 9, 14) + tuple(range(16, 56))
    h = header(raw_header, 4, versions)
    crc = struct.unpack("<I", one(top, 13))[0]
    parts = []
    for expected_number, (number, payload) in enumerate(chunks(one(top, 9))):
        if number != expected_number:
            raise FormatError("Skin part IDs must be sequential")
        part = chunks(payload)
        raw_part_header = one(part, 1)
        if len(raw_part_header) == 64 and raw_part_header[1] == 0:
            # Empty editor placeholders can remain alongside renderable parts.
            continue
        ph = header(raw_part_header, 5, versions)
        if ph[0] != h[0]:
            raise FormatError("Skin part and model header versions differ")
        legacy = h[0] in (7, 9, 14)
        mat = (_material(one(part, 2), False, 0, 3) if legacy else
               _material(one(part, 2), False))
        r = Reader(one(part, 5))
        if version >= 53:
            used_count = r.unpack("<H")[0]
            used = list(r.unpack("<%dH" % used_count))
        else:
            used_count = r.unpack("<B")[0]
            used = list(r.read(used_count))
        boxes = r.read(used_count * 60).tobytes()
        auxiliary = b""
        lods = []
        selected_lod = -1
        if version >= 55:
            r.done()
            lods = _lod_descriptors(one(part, 45))
            valid = [item for item in lods if item.vertex_count and item.face_count]
            if not valid:
                raise FormatError("Skin part has no valid LOD")
            selected = max(valid, key=lambda item: item.ident)
            selected_lod = selected.ident
            raw = geometry_data if geometry_data is not None else one(top, 47)
            vertices, faces, shadow_faces = _lod_geometry(raw, selected)
            vertex_count = selected.vertex_count
        else:
            vertex_count = r.unpack("<I")[0]
            auxiliary_count = r.unpack("<H")[0] if 30 <= version <= 51 else 0
            vertices = []
            for _ in range(vertex_count):
                a = r.unpack("<4h5I2h")
                v = SkinVertex(a[:4], *a[4:9], a[9:11],
                               modern=version >= 47,
                               direct_bones=version >= 49)
                v.influences(used)
                vertices.append(v)
            auxiliary = r.read(auxiliary_count * 16).tobytes()
            r.done()
            r = Reader(one(part, 4))
            main, shadow = r.unpack("<HH")
            if legacy:
                if main % 3 or shadow % 3:
                    raise FormatError("Invalid legacy skin index count")
                main //= 3
                shadow //= 3
            if len(r.data) != 4 + 6 * (main + shadow):
                raise FormatError("Invalid skin triangle count")
            faces = [r.unpack("<3H") for _ in range(main)]
            shadow_faces = [r.unpack("<3H") for _ in range(shadow)]
            if any(i >= vertex_count for f in faces + shadow_faces for i in f):
                raise FormatError("Skin face index out of range")
        parts.append(SkinPart(mat, used, boxes, vertices, faces, shadow_faces,
                              ph, [(i, p) for i, p in part
                                   if i not in (1, 2, 4, 5, 45)],
                              _part_scale(ph), auxiliary, lods, selected_lod))
    return SkinModel(parts, crc, h, [(i, p) for i, p in top if i not in (1, 9, 13)])

def write_mesh(model):
    payloads = []
    all_positions = []
    for part in model.parts:
        part_positions = []
        version = (part.header or model.header)[0]
        if version >= 55:
            raise FormatError("M4 2022 version 55 mesh export is not supported yet")
        maximum_bones = 65535 if version >= 53 else 255
        if len(part.used_bones) > maximum_bones or len(part.bone_boxes) != 60 * len(part.used_bones):
            raise FormatError("Invalid used bones or boxes")
        if len(part.faces) > 65535 or len(part.shadow_faces) > 65535:
            raise FormatError("Too many skin triangles")
        if version >= 53:
            vertex_data = struct.pack("<H", len(part.used_bones))
            vertex_data += struct.pack("<%dH" % len(part.used_bones),
                                       *part.used_bones)
        else:
            vertex_data = struct.pack("<B", len(part.used_bones)) + bytes(part.used_bones)
        vertex_data += part.bone_boxes + struct.pack("<I", len(part.vertices))
        if 30 <= version <= 51:
            if len(part.auxiliary) % 16:
                raise FormatError("Invalid skin auxiliary table")
            vertex_data += struct.pack("<H", len(part.auxiliary) // 16)
        for v in part.vertices:
            v.influences(part.used_bones)
            vertex_data += struct.pack("<4h5I2h", *v.offset, v.normal, v.tangent,
                                       v.binormal, v.bones, v.weights, *v.uv)
            part_positions.append(tuple(x * part.scale / 32768 for x in v.offset[:3]))
        vertex_data += part.auxiliary
        faces = part.faces + part.shadow_faces
        if any(i >= len(part.vertices) or i < 0 for f in faces for i in f):
            raise FormatError("Skin face index out of range")
        ph = part.header or bounds_header(part_positions, 5)
        legacy = ph[0] in (7, 9, 14)
        face_counts = ((len(part.faces) * 3, len(part.shadow_faces) * 3)
                       if legacy else (len(part.faces), len(part.shadow_faces)))
        face_data = struct.pack("<HH", *face_counts)
        face_data += b"".join(struct.pack("<3H", *f) for f in faces)
        material = (_material_bytes(part.material, False, 0, 3) if legacy else
                    _material_bytes(part.material, False))
        payload = pack_chunk(1, ph) + pack_chunk(2, material)
        payload += pack_chunk(5, vertex_data) + pack_chunk(4, face_data)
        payload += b"".join(pack_chunk(i, p) for i, p in part.extra)
        payloads.append(pack_chunk(len(payloads), payload))
        all_positions.extend(part_positions)
    h = model.header or bounds_header(all_positions, 4)
    return (pack_chunk(1, h) + pack_chunk(13, struct.pack("<I", model.bones_crc))
            + pack_chunk(9, b"".join(payloads))
            + b"".join(pack_chunk(i, p) for i, p in model.extra))

