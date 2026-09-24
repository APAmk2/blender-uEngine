import struct
import zlib

from .common import FormatError, Reader


_SCALARS = {
    "u8": ("<B", 1), "bool": ("<B", 1), "bool8": ("<B", 1),
    "u16": ("<H", 2), "u32": ("<I", 4), "flags32": ("<I", 4),
    "fp32": ("<f", 4), "vec3f": ("<3f", 12), "ang3f": ("<3f", 12),
    "vec4f": ("<4f", 16),
}


def _crc(name):
    return zlib.crc32(name.encode("ascii")) & 0xffffffff


def _section(data, expected_name=None, is_array=False):
    reader = Reader(data)
    mode = reader.unpack("<B")[0]
    if not mode & 1:
        raise FormatError("Embedded archive has no debug field names")
    name = reader.stringz()
    if expected_name is not None and name != expected_name:
        raise FormatError("Embedded archive section %r, expected %r" % (name, expected_name))
    if is_array:
        if reader.stringz() != "count" or reader.stringz() != "u32":
            raise FormatError("Invalid embedded archive array count")
        result = []
        for index in range(reader.unpack("<I")[0]):
            record_name = "rec_%04d" % index
            record_crc = reader.unpack("<I")[0]
            size = reader.unpack("<I")[0]
            payload = reader.read(size).tobytes()
            probe = Reader(payload)
            probe.unpack("<B")
            stored_name = probe.stringz()
            # Most arrays use rec_0000, rec_0001, ...; a few archive
            # variants use semantic record names such as col_idles.
            if record_crc != _crc(stored_name):
                raise FormatError("Invalid embedded archive record CRC")
            if stored_name != record_name and stored_name.startswith("rec_"):
                raise FormatError("Invalid embedded archive record name")
            result.append(_section(payload, stored_name))
        reader.done()
        return result
    result = {}
    while reader.pos < len(reader.data):
        # Newer archives append named sub-sections directly to a section.
        # They use the same CRC/size envelope as the archive root, without a
        # field/type pair in front of it.
        first = reader.data[reader.pos]
        if not (65 <= first <= 90 or 97 <= first <= 122 or first == 95):
            section_crc, size = reader.unpack("<II")
            payload = reader.read(size).tobytes()
            probe = Reader(payload)
            if not probe.unpack("<B")[0] & 1:
                raise FormatError("Embedded archive sub-section has no names")
            section_name = probe.stringz()
            if section_crc != _crc(section_name):
                raise FormatError("Invalid embedded archive sub-section CRC")
            # Procedural/editor sections are unrelated to the bind skeleton
            # consumed by the importer and contain SDK-specific field types.
            result[section_name] = payload
            continue
        field = reader.stringz()
        kind = reader.stringz()
        if kind == "stringz":
            value = reader.stringz()
        elif kind == "choose":
            choice_name = reader.stringz()
            choice_kind = reader.stringz()
            if choice_name != field or choice_kind != "stringz":
                raise FormatError("Unsupported embedded archive choice")
            value = reader.stringz()
        elif kind in _SCALARS:
            fmt, _size = _SCALARS[kind]
            values = reader.unpack(fmt)
            value = values[0] if len(values) == 1 else values
        elif kind in ("u8_array", "u32_array"):
            count = reader.unpack("<I")[0]
            value = (reader.read(count).tobytes() if kind == "u8_array" else
                     reader.unpack("<%dI" % count))
        elif kind == "array":
            if reader.unpack("<I")[0] != _crc(field):
                raise FormatError("Invalid embedded archive field CRC")
            size = reader.unpack("<I")[0]
            value = _section(reader.read(size).tobytes(), field, True)
        else:
            raise FormatError(
                "Unsupported embedded archive type %r for field %r at 0x%x" %
                (kind, field, reader.pos)
            )
        result[field] = value
    return result


def read_archive(data, expected_name):
    reader = Reader(data)
    mode = reader.unpack("<B")[0]
    if not mode & 1 or reader.unpack("<I")[0] != _crc(expected_name):
        raise FormatError("Invalid embedded %s archive" % expected_name)
    size = reader.unpack("<I")[0]
    result = _section(reader.read(size).tobytes(), expected_name)
    reader.done()
    return result


def read_skeleton(data):
    """Convert an embedded typed skeleton archive to shared skeleton records."""
    from .skeleton import Bone, Locator, Skeleton
    root = read_archive(data, "skeleton")
    bones = [Bone(item["name"], item.get("parent", ""), tuple(item["q"]),
                  tuple(item["t"]), int(item.get("bp", 0)))
             for item in root.get("bones", [])]
    locators = [Locator(item["name"], item.get("parent", ""), tuple(item["q"]),
                        tuple(item["t"]), int(item.get("fl", 0)))
                for item in root.get("locators", [])]
    partitions = []
    for item in root.get("partitions", []):
        influence = bytes(item["infl"])
        if len(influence) < len(bones):
            raise FormatError("Embedded skeleton partition is shorter than its bone list")
        # M3/M4 archives can append masks for auxiliary and procedural bones.
        # Those bones are stored in later archive sections and are not part of
        # the bind skeleton imported into Blender.
        partitions.append((item["name"], influence[:len(bones)]))
    params = [(item["name"], float(item["b"]), float(item["e"]),
               float(item["loop"])) for item in root.get("params", [])]
    return Skeleton(bones, int(root.get("crc", 0)), locators, partitions, params,
                    str(root.get("motions", "")))
