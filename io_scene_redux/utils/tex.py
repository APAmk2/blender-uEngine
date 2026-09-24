import hashlib
from pathlib import Path
import re
import struct
import subprocess
import tempfile


SOURCE_EXTENSIONS = (".png", ".tga", ".psd", ".jpg", ".jpeg",
                     ".tif", ".tiff", ".bmp", ".dds")
TIER_EXTENSIONS = (".4096", ".2048", ".1024", ".512", ".64")

_DDS_FORMATS = {
    0: (b"DXT1", 8, None),       # Redux BC1
    1: (b"DXT5", 16, None),      # Redux BC3
    5: (b"DX10", 16, 98),        # M3/M4 BC7 UNORM
}


def normalize_tex_relpath(name):
    parts = name.replace("/", "\\").split("\\")
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise ValueError("Invalid Redux texture path")
    return parts


def make_abs_tex_path(content_root, texture_name):
    path = Path(content_root).joinpath("textures", *normalize_tex_relpath(texture_name))
    return Path(str(path) + ".png")


def texture_candidates(content_root, texture_name):
    """Source images for one Redux texture name, in preferred order."""
    base = Path(content_root).joinpath("textures", *normalize_tex_relpath(texture_name))
    if base.suffix.lower() in SOURCE_EXTENSIONS:
        yield base
        base = base.with_suffix("")
    for extension in SOURCE_EXTENSIONS:
        yield Path(str(base) + extension)


def _texture_metadata(base):
    path = Path(str(base) + ".lua")
    if not path.is_file():
        return None
    source = path.read_text(encoding="utf-8", errors="replace")
    values = {}
    for name in ("format", "width", "height"):
        match = re.search(r"(?m)^\s*%s\s*=\s*(\d+)\s*," % name, source)
        if not match:
            return None
        values[name] = int(match.group(1))
    srgb = re.search(r"(?m)^\s*mip_srgb\s*=\s*true\s*,", source) is not None
    return values["format"], values["width"], values["height"], srgb


def _lz4_block(data, max_output=None):
    """Decode the raw LZ4 blocks used by M3 and M4 texture tiers."""
    source = memoryview(data)
    result = bytearray()
    offset = 0
    while offset < len(source):
        token = source[offset]
        offset += 1
        literal_count = token >> 4
        if literal_count == 15:
            while True:
                if offset >= len(source):
                    raise ValueError("Truncated LZ4 literal length")
                value = source[offset]
                offset += 1
                literal_count += value
                if value != 255:
                    break
        if offset + literal_count > len(source):
            raise ValueError("Truncated LZ4 literals")
        if max_output is not None and len(result) + literal_count >= max_output:
            needed = max_output - len(result)
            result.extend(source[offset:offset + needed])
            return bytes(result)
        result.extend(source[offset:offset + literal_count])
        offset += literal_count
        if offset == len(source):
            break
        if offset + 2 > len(source):
            raise ValueError("Truncated LZ4 match")
        distance = source[offset] | source[offset + 1] << 8
        offset += 2
        if not distance or distance > len(result):
            raise ValueError("Invalid LZ4 match distance")
        match_count = (token & 15) + 4
        if (token & 15) == 15:
            while True:
                if offset >= len(source):
                    raise ValueError("Truncated LZ4 match length")
                value = source[offset]
                offset += 1
                match_count += value
                if value != 255:
                    break
        for _index in range(match_count):
            result.append(result[-distance])
            if max_output is not None and len(result) >= max_output:
                return bytes(result)
    return bytes(result)


def _tier_dimensions(width, height, limit):
    largest = max(width, height)
    if largest <= limit:
        return width, height
    return (max(1, width * limit // largest),
            max(1, height * limit // largest))


def _dds(data, width, height, fourcc, block_size, dxgi_format=None):
    linear_size = max(1, (width + 3) // 4) * max(1, (height + 3) // 4) * block_size
    flags = 0x00081007  # caps, height, width, pixel format, linear size
    header = struct.pack("<7I", 124, flags, height, width, linear_size, 0, 1)
    header += bytes(44)
    header += struct.pack("<2I4s5I", 32, 4, fourcc, 0, 0, 0, 0, 0)
    header += struct.pack("<5I", 0x1000, 0, 0, 0, 0)
    if dxgi_format is not None:
        header += struct.pack("<5I", dxgi_format, 3, 0, 1, 0)
    return b"DDS " + header + data[:linear_size]


def compiled_texture_dds(content_root, texture_name):
    """Return a Blender-readable DDS and its engine tier source path."""
    base = Path(content_root).joinpath("textures", *normalize_tex_relpath(texture_name))
    if base.suffix.lower() in SOURCE_EXTENSIONS:
        base = base.with_suffix("")
    metadata = _texture_metadata(base)
    if metadata is None or metadata[0] not in _DDS_FORMATS:
        return None, None
    texture_format, width, height, srgb = metadata
    fourcc, block_size, dxgi_format = _DDS_FORMATS[texture_format]
    if texture_format == 5 and srgb:
        dxgi_format = 99  # DXGI_FORMAT_BC7_UNORM_SRGB
    for extension in TIER_EXTENSIONS:
        path = Path(str(base) + extension)
        if not path.is_file():
            continue
        limit = int(extension[1:])
        tier_width, tier_height = _tier_dimensions(width, height, limit)
        expected = (max(1, (tier_width + 3) // 4) *
                    max(1, (tier_height + 3) // 4) * block_size)
        packed = path.read_bytes()
        data = packed
        if texture_format == 5 and len(packed) != expected:
            try:
                decoded = _lz4_block(packed, expected)
                if len(decoded) >= expected:
                    data = decoded
            except ValueError:
                pass
        if len(data) >= expected:
            return (_dds(data, tier_width, tier_height, fourcc, block_size,
                         dxgi_format), path)
    return None, None


def _compiled_cache_path(source_path, data):
    stat = source_path.stat()
    identity = "%s|%d|%d" % (source_path.resolve(), stat.st_mtime_ns, stat.st_size)
    digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()
    directory = Path(tempfile.gettempdir()) / "blender-uengine-textures"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (digest + ".dds")
    if not path.is_file() or path.stat().st_size != len(data):
        path.write_bytes(data)
    return path


def _sdk_texconv(content_root):
    root = Path(content_root).resolve()
    bundled = Path(__file__).resolve().parent.parent / "bin" / "texconv.exe"
    candidates = (bundled,
                  root.parent / "bin_x64" / "texconv.exe",
                  root.parent.parent / "bin_x64" / "texconv.exe")
    return next((path for path in candidates if path.is_file()), None)


def _convert_dds_to_png(content_root, dds_path):
    """Use the SDK converter when Blender cannot decode BC7 DDS directly."""
    converter = _sdk_texconv(content_root)
    if converter is None:
        return None
    output = dds_path.with_suffix(".PNG")
    if output.is_file():
        return output
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(
            [str(converter), "-nologo", "-ft", "png", "-o",
             str(dds_path.parent), str(dds_path)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=creationflags, timeout=120, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode:
        return None
    if output.is_file():
        return output
    lower = dds_path.with_suffix(".png")
    return lower if lower.is_file() else None


def load_image_by_tex_path(path):
    import bpy
    if not path.is_file():
        return None
    try:
        image = bpy.data.images.load(str(path), check_existing=True)
        return image if all(image.size) else None
    except RuntimeError:
        return None


def load_texture_image(content_root, texture_name):
    for path in texture_candidates(content_root, texture_name):
        image = load_image_by_tex_path(path)
        if image is not None:
            return image, path
    data, source_path = compiled_texture_dds(content_root, texture_name)
    if data is not None:
        dds_path = _compiled_cache_path(source_path, data)
        image = load_image_by_tex_path(dds_path)
        if image is None:
            png_path = _convert_dds_to_png(content_root, dds_path)
            image = load_image_by_tex_path(png_path) if png_path else None
        if image is not None:
            image.name = source_path.name
            return image, source_path
    return None, None
