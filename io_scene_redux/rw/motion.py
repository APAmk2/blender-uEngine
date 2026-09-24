"""4A Engine compiled .m2 motion reader.

The mixed-endian curve layout is described in MetroFormats/ANIMATION.md.
This module has no Blender dependency.
"""

from dataclasses import dataclass
import math
import struct

from .common import FormatError, Reader, chunks, one


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
