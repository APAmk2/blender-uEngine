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

    def influences(self, used_bones):
        result = []
        if not 1 <= self.offset[3] <= 4:
            raise FormatError("Invalid skin influence slot count")
        # The shader swizzles packed COLOR bytes .zyxw for both IDs and weights.
        for slot in (2, 1, 0, 3)[:self.offset[3]]:
            idx = (self.bones >> (slot * 8)) & 255
            weight = (self.weights >> (slot * 8)) & 255
            if idx % 3 or idx // 3 >= len(used_bones):
                raise FormatError("Invalid packed bone index")
            if weight:
                result.append((used_bones[idx // 3], weight / 255))
        return result

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

@dataclass
class SkinModel:
    parts: list
    bones_crc: int
    header: bytes = b""
    extra: list = field(default_factory=list)

def read_mesh(data):
    top = chunks(data)
    raw_header = one(top, 1)
    if raw_header[:2] == bytes((16, 0)):
        h = header(raw_header, 0, (16,))
        crc = struct.unpack("<I", one(top, 13))[0]
        if one(top, 9):
            raise FormatError("Empty skin placeholder contains parts")
        return SkinModel([], crc, h,
                         [(i, p) for i, p in top if i not in (1, 9, 13)])
    h = header(raw_header, 4, (7, 9, 14, 21, 22, 23))
    crc = struct.unpack("<I", one(top, 13))[0]
    parts = []
    for number, payload in chunks(one(top, 9)):
        if number != len(parts):
            raise FormatError("Skin part IDs must be sequential")
        part = chunks(payload)
        ph = header(one(part, 1), 5, (7, 9, 14, 21, 22, 23))
        if ph[0] != h[0]:
            raise FormatError("Skin part and model header versions differ")
        legacy = h[0] in (7, 9, 14)
        mat = (_material(one(part, 2), False, 0, 3) if legacy else
               _material(one(part, 2), False))
        r = Reader(one(part, 5))
        used_count = r.unpack("<B")[0]
        used = list(r.read(used_count))
        boxes = r.read(used_count * 60).tobytes()
        vertex_count = r.unpack("<I")[0]
        if len(r.data) - r.pos != vertex_count * 32:
            raise FormatError("Invalid skin vertex count")
        vertices = []
        for _ in range(vertex_count):
            a = r.unpack("<4h5I2h")
            v = SkinVertex(a[:4], *a[4:9], a[9:11])
            v.influences(used)
            vertices.append(v)
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
                              ph, [(i, p) for i, p in part if i not in (1, 2, 4, 5)]))
    return SkinModel(parts, crc, h, [(i, p) for i, p in top if i not in (1, 9, 13)])

def write_mesh(model):
    payloads = []
    all_positions = []
    for part in model.parts:
        part_positions = []
        if len(part.used_bones) > 255 or len(part.bone_boxes) != 60 * len(part.used_bones):
            raise FormatError("Invalid used bones or boxes")
        if len(part.faces) > 65535 or len(part.shadow_faces) > 65535:
            raise FormatError("Too many skin triangles")
        vertex_data = struct.pack("<B", len(part.used_bones)) + bytes(part.used_bones)
        vertex_data += part.bone_boxes + struct.pack("<I", len(part.vertices))
        for v in part.vertices:
            v.influences(part.used_bones)
            vertex_data += struct.pack("<4h5I2h", *v.offset, v.normal, v.tangent,
                                       v.binormal, v.bones, v.weights, *v.uv)
            part_positions.append(tuple(x * 12 / 32767 for x in v.offset[:3]))
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

