"""4A Engine compiled .m2 motion reader.

The mixed-endian curve layout is described in MetroFormats/ANIMATION.md.
This module has no Blender dependency.
"""

from dataclasses import dataclass
import math
import struct

from .common import FormatError, Reader, chunks, one, pack_chunk


@dataclass
class Curve:
    format: int
    dimensions: int
    times: tuple
    values: tuple

    def sample(self, time):
        if not self.values:
            if self.dimensions == 4:
                return (0.0, 0.0, 0.0, 1.0)
            if self.dimensions == 3:
                return (0.0, 0.0, 0.0)
            return (0.0,) * self.dimensions
        if len(self.values) == 1 or not self.times:
            return self.values[0]
        if time <= self.times[0]:
            return self.values[0]
        for index in range(1, len(self.times)):
            if time <= self.times[index]:
                before, after = self.times[index - 1:index + 1]
                factor = (time - before) / (after - before) if after > before else 0
                a, b = self.values[index - 1:index + 1]
                if self.dimensions == 4:
                    # Unit quaternion interpolation, including the short arc.
                    dot = sum(x * y for x, y in zip(a, b))
                    if dot < 0:
                        b = tuple(-x for x in b)
                        dot = -dot
                    if dot > 0.9995:
                        result = tuple((1 - factor) * x + factor * y for x, y in zip(a, b))
                        norm = math.sqrt(sum(x * x for x in result))
                        return tuple(x / norm for x in result)
                    theta = math.acos(max(-1, min(1, dot)))
                    divisor = math.sin(theta)
                    left = math.sin((1 - factor) * theta) / divisor
                    right = math.sin(factor * theta) / divisor
                    return tuple(left * x + right * y for x, y in zip(a, b))
                return tuple((1 - factor) * x + factor * y for x, y in zip(a, b))
        return self.values[-1]


@dataclass
class Motion:
    bones_crc: int
    bones_count: int
    frame_start: int
    frame_total: int
    position_offset: tuple
    speed: float
    animated_bones: tuple
    bone_curves: tuple
    locator_names: tuple
    curves: tuple


def _read_curve(payload, offset, next_offset, endian):
    if offset < 0 or next_offset > len(payload) or next_offset <= offset:
        raise FormatError("Invalid .m2 curve offset")
    reader = Reader(payload[offset:next_offset])
    header = reader.unpack(endian + "I")[0]
    count = header & 0xffff
    format_id = (header >> 16) & 15
    dimensions = (header >> 24) & 15
    times = ()
    values = ()
    if format_id == 1:
        times = reader.unpack(endian + "%df" % count)
        values = tuple(reader.unpack(endian + "%df" % dimensions) for _ in range(count))
    elif format_id == 2:
        values = tuple(reader.unpack(endian + "%df" % dimensions) for _ in range(count))
    elif format_id == 3:
        values = tuple(reader.unpack(endian + "%dH" % dimensions) for _ in range(count))
    elif format_id == 4:
        if dimensions != 3:
            raise FormatError("Vector3 curve has %d dimensions" % dimensions)
        inverse_scale = reader.unpack(endian + "f")[0]
        scale = reader.unpack(endian + "3f")
        base = reader.unpack(endian + "3f")
        knots = reader.unpack(endian + "%dH" % count)
        times = tuple(k / inverse_scale for k in knots)
        values = tuple(tuple(raw[i] * scale[i] + base[i] for i in range(3))
                       for raw in (reader.unpack(endian + "3H") for _ in range(count)))
    elif format_id == 5:
        if dimensions != 4:
            raise FormatError("Quaternion curve has %d dimensions" % dimensions)
        inverse_scale = reader.unpack(endian + "f")[0]
        knots = reader.unpack(endian + "%dH" % count)
        times = tuple(k / inverse_scale for k in knots)
        decoded = []
        for _ in range(count):
            words = reader.unpack(endian + "3H")
            omitted = 2 * (words[0] & 1) + (words[1] & 1)
            signed = tuple(word - 65536 if word & 32768 else word for word in words)
            stored = tuple(word / (32768 * math.sqrt(2)) for word in signed)
            missing = math.sqrt(max(0.0, 1.0 - sum(x * x for x in stored)))
            if words[2] & 1:
                missing = -missing
            decoded.append(tuple(stored[:omitted] + (missing,) + stored[omitted:]))
        values = tuple(decoded)
    elif format_id == 6:
        inverse_scale = reader.unpack(endian + "f")[0]
        knots = reader.unpack(endian + "%dH" % count)
        times = tuple(k / inverse_scale for k in knots)
        values = tuple((reader.unpack(endian + "H")[0],) for _ in range(count))
    elif format_id == 7:
        if count:
            raise FormatError("Identity curve has nonzero knot count")
    else:
        raise FormatError("Unsupported .m2 curve format %d" % format_id)
    expected = (reader.pos + 3) & ~3
    if expected != len(reader.data):
        raise FormatError(".m2 curve size mismatch")
    return Curve(format_id, dimensions, tuple(times), tuple(values))


def read_m2(data):
    top = chunks(data)
    header = one(top, 0)
    if len(header) < 4:
        raise FormatError("Truncated .m2 header")
    version = struct.unpack_from("<I", header)[0]
    if version == 15:
        if len(header) != 30:
            raise FormatError("Expected version 15 .m2 header")
        version, crc, bones_count, quality, start, total, px, py, pz = struct.unpack(
            "<IIHIHH3f", header)
        mask_words = 4
        curve_header_size = 32
        curve_endian = None
        settings_size = 62
        data_size_offset = 38
        has_locator_references = False
    elif version in (16, 17):
        if len(header) != 30:
            raise FormatError("Expected version %d .m2 header" % version)
        version, crc, bones_count, quality, start, total, px, py, pz = struct.unpack(
            "<IIHIHH3f", header)
        mask_words = 8
        curve_header_size = 48
        curve_endian = "<"
        settings_size = 94
        data_size_offset = 54
        has_locator_references = version >= 17
    elif version in (18, 19):
        if len(header) != 42:
            raise FormatError("Expected version %d .m2 header" % version)
        values = struct.unpack("<IIHIHH6f", header)
        _version, crc, bones_count, quality, start, total = values[:6]
        px, py, pz = values[6:9]
        mask_words = 8
        curve_header_size = 48
        curve_endian = "<"
        settings_size = 94 if version == 18 else 98
        data_size_offset = 54 if version == 18 else 58
        has_locator_references = True
    else:
        raise FormatError("Unsupported .m2 version %d" % version)
    settings = one(top, 1)
    if len(settings) != settings_size:
        raise FormatError("Expected version %d .m2 settings" % version)
    speed = struct.unpack_from("<f", settings, 2)[0]
    data_size, offsets_size = struct.unpack_from("<II", settings, data_size_offset)
    payload = one(top, 9)
    if data_size != len(payload):
        raise FormatError(".m2 data size mismatch")
    if len(payload) < curve_header_size:
        raise FormatError("Truncated .m2 curve header")
    mask_endian = ">" if version == 15 else "<"
    words = struct.unpack_from(mask_endian + "%dI" % mask_words, payload)
    animated = tuple(i for i in range(bones_count)
                     if i < mask_words * 32 and (words[i // 32] >> (i % 32)) & 1)
    if sum(word.bit_count() for word in words) != len(animated):
        raise FormatError("Animated bone bit exceeds skeleton bone count")
    metadata_offset = mask_words * 4
    locator_count, transform_present = struct.unpack_from(
        mask_endian + "2H", payload, metadata_offset)
    expected_size = struct.unpack_from(mask_endian + "I", payload,
                                       metadata_offset + 4)[0]
    if expected_size != len(payload):
        raise FormatError(".m2 curve header size mismatch")
    count = 3 * len(animated) + 4 * locator_count + 3 * bool(transform_present)
    big_count = 2 * len(animated) + 3 * locator_count + 2 * bool(transform_present)
    if offsets_size != curve_header_size + 4 * count:
        raise FormatError(".m2 curve offset table size mismatch")
    offsets = [struct.unpack_from(
        (curve_endian or (">" if i < big_count else "<")) + "I",
        payload, curve_header_size + 4 * i)[0] for i in range(count)]
    if offsets and offsets[0] != offsets_size:
        raise FormatError(".m2 curve table does not meet curve data")
    curves = []
    for i, offset in enumerate(offsets):
        end = offsets[i + 1] if i + 1 < len(offsets) else len(payload)
        endian = curve_endian or (">" if i < big_count else "<")
        curves.append(_read_curve(payload, offset, end, endian))
    locators = Reader(one(top, 10))
    names = []
    if locators.unpack("<H")[0] != locator_count:
        raise FormatError(".m2 locator count mismatch")
    for _ in range(locator_count):
        names.append(locators.stringz())
        locators.read(1)  # flags
    if has_locator_references:
        reference_count = locators.unpack("<H")[0]
        for _ in range(reference_count):
            locators.stringz()
    locators.done()
    return Motion(crc, bones_count, start, total, (px, py, pz), speed,
                  animated, tuple(tuple(curves[3*i:3*i+3]) for i in range(len(animated))),
                  tuple(names), tuple(curves))


def _curve_bytes(curve, endian):
    count = len(curve.values)
    if any(len(value) != curve.dimensions for value in curve.values):
        raise FormatError(".m2 curve value has the wrong dimension")
    if any(not math.isfinite(component) for value in curve.values for component in value):
        raise FormatError(".m2 curve contains a non-finite value")
    if any(not math.isfinite(time) or time < 0 for time in curve.times):
        raise FormatError(".m2 curve contains an invalid time")
    if curve.format == 1:
        if count != len(curve.times) or not count:
            raise FormatError("Sampled .m2 curve needs matching times and values")
        payload = struct.pack(endian + "%df" % count, *curve.times)
        payload += b"".join(struct.pack(endian + "%df" % curve.dimensions, *value)
                            for value in curve.values)
    elif curve.format == 2:
        if not count:
            raise FormatError("Constant .m2 curve has no value")
        payload = b"".join(struct.pack(endian + "%df" % curve.dimensions, *value)
                            for value in curve.values)
    elif curve.format == 4:
        if curve.dimensions != 3 or count != len(curve.times) or not count:
            raise FormatError("Compressed vector curve needs timed 3D values")
        inverse_scale, knots = _curve_knots(curve.times)
        minimum = tuple(min(value[axis] for value in curve.values) for axis in range(3))
        maximum = tuple(max(value[axis] for value in curve.values) for axis in range(3))
        scale = tuple((high - low) / 65535.0 if high != low else 1.0
                      for low, high in zip(minimum, maximum))
        controls = [tuple(max(0, min(65535, round(
            (value[axis] - minimum[axis]) / scale[axis]))) for axis in range(3))
                    for value in curve.values]
        payload = struct.pack(endian + "f3f3f", inverse_scale, *scale, *minimum)
        payload += struct.pack(endian + "%dH" % count, *knots)
        payload += b"".join(struct.pack(endian + "3H", *value)
                            for value in controls)
    elif curve.format == 5:
        if curve.dimensions != 4 or count != len(curve.times) or not count:
            raise FormatError("Compressed quaternion curve needs timed 4D values")
        inverse_scale, knots = _curve_knots(curve.times)
        controls = []
        factor = 32768.0 * math.sqrt(2.0)
        for value in curve.values:
            length = math.sqrt(sum(component * component for component in value))
            if length <= 1e-20:
                raise FormatError(".m2 quaternion curve contains a zero quaternion")
            normalized = tuple(component / length for component in value)
            omitted = max(range(4), key=lambda index: abs(normalized[index]))
            stored = [normalized[index] for index in range(4) if index != omitted]
            words = [max(-32768, min(32767, round(component * factor)))
                     for component in stored]
            metadata = (omitted >> 1, omitted & 1,
                        1 if normalized[omitted] < 0 else 0)
            words = [((word & 0xffff) & 0xfffe) | bit
                     for word, bit in zip(words, metadata)]
            controls.append(tuple(words))
        payload = struct.pack(endian + "f", inverse_scale)
        payload += struct.pack(endian + "%dH" % count, *knots)
        payload += b"".join(struct.pack(endian + "3H", *value)
                            for value in controls)
    elif curve.format == 7:
        if count or curve.times:
            raise FormatError("Identity .m2 curve contains keys")
        payload = b""
    else:
        raise FormatError("Unsupported .m2 export curve format %d" % curve.format)
    degree = 2 if curve.format in (4, 5) else 0
    flags = 1 if curve.dimensions == 4 else 0
    header = (count | (curve.format << 16) | (degree << 20) |
              (curve.dimensions << 24) | (flags << 28))
    result = struct.pack(endian + "I", header) + payload
    return result + bytes((-len(result)) & 3)


def _curve_knots(times):
    if all(abs(time * 30.0 - round(time * 30.0)) <= 1e-4 and
           round(time * 30.0) <= 65535 for time in times):
        inverse_scale = 30.0
    else:
        maximum = max(times)
        inverse_scale = 1.0 if maximum == 0 else 65535.0 / maximum
    knots = tuple(max(0, min(65535, round(time * inverse_scale))) for time in times)
    if any(after <= before for before, after in zip(knots, knots[1:])):
        raise FormatError(".m2 curve times cannot be represented as increasing knots")
    return inverse_scale, knots


def write_m2(clip, version=15, extra_chunks=()):
    if version not in (15, 16, 17, 18, 19):
        raise FormatError("Unsupported .m2 export version %d" % version)
    mask_words = 4 if version == 15 else 8
    capacity = mask_words * 32
    if not 0 < clip.bones_count <= 0xffff:
        raise FormatError("Invalid .m2 skeleton bone count")
    if not 0 <= clip.frame_start <= 0xffff or not 0 < clip.frame_total <= 0xffff:
        raise FormatError("Invalid .m2 frame range")
    if len(clip.animated_bones) != len(clip.bone_curves):
        raise FormatError(".m2 animated bone and curve counts differ")
    if tuple(sorted(set(clip.animated_bones))) != tuple(clip.animated_bones):
        raise FormatError(".m2 animated bone IDs must be unique and sorted")
    if any(index < 0 or index >= clip.bones_count or index >= capacity
           for index in clip.animated_bones):
        raise FormatError("Animated bone exceeds the .m2 mask capacity")
    if clip.locator_names:
        raise FormatError("Animated locator export is not supported")
    if len(clip.position_offset) != 3 or any(
            not math.isfinite(value) for value in clip.position_offset):
        raise FormatError("Invalid .m2 position offset")
    if not math.isfinite(clip.speed):
        raise FormatError("Invalid .m2 playback speed")

    curves = []
    for group in clip.bone_curves:
        if len(group) != 3 or group[0].dimensions != 4 or group[1].dimensions != 3:
            raise FormatError("Invalid .m2 bone curves")
        curves.extend(group)
    header_size = 32 if version == 15 else 48
    offset_table_size = header_size + 4 * len(curves)
    big_count = 2 * len(clip.animated_bones) if version == 15 else 0
    records = [_curve_bytes(curve, ">" if index < big_count else "<")
               for index, curve in enumerate(curves)]
    offsets = []
    cursor = offset_table_size
    for record in records:
        offsets.append(cursor)
        cursor += len(record)
    words = [0] * mask_words
    for bone_id in clip.animated_bones:
        words[bone_id // 32] |= 1 << (bone_id % 32)
    if version == 15:
        curve_data = struct.pack(">4I2HI2I", *words, 0, 0, cursor,
                                 0x3f800000, 0x3f800000)
        curve_data += b"".join(struct.pack(">I" if index < big_count else "<I", offset)
                               for index, offset in enumerate(offsets))
    else:
        curve_data = struct.pack("<8I2HI2I", *words, 0, 0, cursor,
                                 0x3f800000, 0x3f800000)
        curve_data += b"".join(struct.pack("<I", offset) for offset in offsets)
    curve_data += b"".join(records)

    quality = 0 if version == 15 else 6
    base_header = struct.pack("<IIHIHH3f", version, clip.bones_crc,
                              clip.bones_count, quality, clip.frame_start,
                              clip.frame_total, *clip.position_offset)
    if version >= 18:
        base_header += struct.pack("<3f", 0.0, 0.0, 0.0)
    settings_size = 62 if version == 15 else (98 if version == 19 else 94)
    settings = bytearray(settings_size)
    struct.pack_into("<HfffIHH", settings, 0, 0x4000, clip.speed,
                     20.0, 20.0, clip.frame_total, 0, 0)
    filter_offset = 22 + (4 if version == 19 else 0)
    valid_words = []
    for word_index in range(mask_words):
        remaining = clip.bones_count - word_index * 32
        valid_words.append(0xffffffff if remaining >= 32 else
                           ((1 << max(0, remaining)) - 1))
    struct.pack_into("<%dI" % mask_words, settings, filter_offset, *valid_words)
    size_offset = 38 if version == 15 else (58 if version == 19 else 54)
    struct.pack_into("<II", settings, size_offset, len(curve_data), offset_table_size)
    struct.pack_into("<%dI" % mask_words, settings, size_offset + 8, *words)

    locator_data = struct.pack("<H", 0)
    if version >= 17:
        locator_data += struct.pack("<H", 0)
    if any(ident not in (6, 7, 8) for ident, _payload in extra_chunks):
        raise FormatError("Invalid optional .m2 chunk")
    return (pack_chunk(0, base_header) + pack_chunk(1, bytes(settings)) +
            pack_chunk(9, curve_data) + pack_chunk(10, locator_data) +
            b"".join(pack_chunk(ident, payload)
                     for ident, payload in extra_chunks))
