from dataclasses import dataclass
import struct
from ..utils.formats_io import (FormatError, Reader, ChunkedReader,
                                pack_chunk, stringz)
from ..utils.mesh import calculate_mesh_bbox, calculate_mesh_bsphere

def chunks(data):
    return list(ChunkedReader(data))

def one(items, ident):
    values = [payload for key, payload in items if key == ident]
    if len(values) != 1:
        raise FormatError("Expected one chunk %d; found %d" % (ident, len(values)))
    return values[0]

def header(data, expected_type, versions=(22,)):
    if len(data) != 64:
        raise FormatError("Model header must be 64 bytes")
    if data[0] not in versions or data[1] != expected_type:
        raise FormatError("Unsupported model version/type %d/%d" % (data[0], data[1]))
    return data

def bounds_header(positions, model_type, original=None):
    """Update bounds, retaining the source version and undocumented fields."""
    if not positions:
        raise FormatError("Cannot export an empty mesh")
    (mins, maxs) = calculate_mesh_bbox(positions)
    center, radius = calculate_mesh_bsphere((mins, maxs), positions)
    result = bytearray(original if original is not None else bytes(64))
    if len(result) != 64:
        raise FormatError("Bad original header")
    version = (result[0] if original is not None and
               result[0] in (7, 8, 9, 14, 16, 17, 18, 20, 21, 22, 23)
               else 22)
    result[0:4] = struct.pack("<BBH", version, model_type, 0xffff)
    result[4:44] = struct.pack("<10f", *mins, *maxs, *center, radius)
    return bytes(result)

@dataclass
class Material:
    texture: str = ""
    shader: str = "geometry\\default"
    game_material: str = "default"
    name: str = "material"
    flags: int = 0
    lmd: float = 1.0

def _material(data, is_static, flags_size=2, string_count=4):
    reader = Reader(data)
    values = [reader.stringz() for _ in range(string_count)]
    values.extend([""] * (4 - len(values)))
    lmd = reader.unpack("<f")[0] if is_static else 1.0
    if flags_size == 0:
        reader.done()
        return Material(*values, flags=0, lmd=lmd)
    flag_format = {1: "<B", 2: "<H", 4: "<I"}.get(flags_size)
    if flag_format is None:
        raise FormatError("Unsupported material flag size")
    flags = reader.unpack(flag_format)[0]
    reader.done()
    return Material(*values, flags=flags, lmd=lmd)

def _material_bytes(material, is_static, flags_size=2, string_count=4):
    values = (material.texture, material.shader, material.game_material, material.name)
    result = b"".join(stringz(v) for v in values[:string_count])
    if is_static:
        result += struct.pack("<f", material.lmd)
    if flags_size == 0:
        return result
    flag_format = {1: "<B", 2: "<H", 4: "<I"}.get(flags_size)
    if flag_format is None:
        raise FormatError("Unsupported material flag size")
    return result + struct.pack(flag_format, material.flags)

