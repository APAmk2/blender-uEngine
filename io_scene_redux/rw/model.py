from dataclasses import dataclass, field
from pathlib import Path

from .common import FormatError, Reader, chunks, one


@dataclass
class Model:
    version: int
    model_type: int
    header: bytes
    lods: list = field(default_factory=list)
    skeleton_key: str = ""
    embedded_mesh: bytes = b""
    embedded_meshes: list = field(default_factory=list)
    embedded_lods: list = field(default_factory=list)
    embedded_skeleton: bytes = b""
    raw_geometry: bytes = b""
    extra: list = field(default_factory=list)


def resource_path(meshes, source_path, key, extension):
    """Resolve a model resource key within the SDK meshes directory."""
    parts = key.replace("/", "\\").split("\\")
    if parts and parts[0] == ".":
        base = Path(source_path).parent
        parts = parts[1:]
    else:
        base = Path(meshes)
    if (not parts or any(part in ("", ".", "..") or ":" in part
                         for part in parts)):
        raise FormatError("Invalid .model resource key %r" % key)
    path = base.joinpath(*parts)
    if path.suffix.lower() != extension:
        path = Path(str(path) + extension)
    path = path.resolve()
    try:
        path.relative_to(Path(meshes).resolve())
    except ValueError:
        raise FormatError("Invalid .model resource key %r" % key) from None
    if not path.is_file():
        raise FormatError("Referenced resource %r was not found" % key)
    return path


def _embedded_meshes(payload, version):
    """Unwrap the LOD slots and mesh entries inside model chunk 15."""
    result = []
    slots = chunks(payload)
    if version >= 55:
        for expected, (ident, mesh_payload) in enumerate(slots):
            if ident != expected:
                raise FormatError("Embedded .model meshes must be sequential")
        return [[mesh_payload for _ident, mesh_payload in slots]]
    for expected, (ident, slot) in enumerate(slots):
        if ident != expected:
            raise FormatError("Embedded .model mesh slots must be sequential")
        meshes = []
        for mesh_index, (mesh_ident, mesh_payload) in enumerate(chunks(slot)):
            if mesh_ident != mesh_index:
                raise FormatError("Embedded .model meshes must be sequential")
            meshes.append(mesh_payload)
        result.append(meshes)
    return result


def read_model(data):
    top = chunks(data)
    header = one(top, 1)
    if len(header) != 64:
        raise FormatError("Model header must be 64 bytes")
    version, model_type = header[:2]
    if model_type == 8:
        raise FormatError("Redux soft-body .model type 8 is not supported")
    supported = ((model_type == 1 and (version == 7 or 11 <= version <= 55)) or
                 (model_type in (2, 3) and 9 <= version <= 55))
    if not supported:
        raise FormatError("Unsupported .model version/type %d/%d" % (version, model_type))
    payloads = dict(top)
    lods = []
    if 16 in payloads:
        reader = Reader(payloads[16])
        if version >= 55:
            lods.append([item.strip().replace("/", "\\")
                         for item in reader.stringz().split(",") if item.strip()])
        else:
            count = reader.unpack("<I")[0]
            if count > 256:
                raise FormatError("Invalid .model LOD count")
            for _ in range(count):
                lods.append([item.strip().replace("/", "\\")
                             for item in reader.stringz().split(",") if item.strip()])
        reader.done()
    skeleton_key = ""
    if 20 in payloads:
        reader = Reader(payloads[20])
        skeleton_key = reader.stringz().replace("/", "\\")
        reader.done()
    embedded_lods = (_embedded_meshes(payloads[15], version) if 15 in payloads else [])
    embedded_meshes = embedded_lods[0] if embedded_lods else []
    return Model(version=version, model_type=model_type, header=header,
                 lods=lods, skeleton_key=skeleton_key,
                 embedded_mesh=embedded_meshes[0] if embedded_meshes else b"",
                 embedded_meshes=embedded_meshes,
                 embedded_lods=embedded_lods,
                 embedded_skeleton=payloads.get(24, b""),
                 raw_geometry=payloads.get(47, b""),
                 extra=[(ident, payload) for ident, payload in top
                        if ident not in (1, 15, 16, 20, 24, 47)])
