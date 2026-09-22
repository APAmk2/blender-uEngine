from dataclasses import dataclass, field

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
    extra: list = field(default_factory=list)


def _embedded_meshes(payload):
    """Unwrap the LOD slots and mesh entries inside model chunk 15."""
    result = []
    slots = chunks(payload)
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
    supported = ((model_type == 1 and version in (7, 17, 20, 21, 22, 23)) or
                 (model_type in (2, 3) and version in (21, 22, 23)))
    if not supported:
        raise FormatError("Unsupported .model version/type %d/%d" % (version, model_type))
    payloads = dict(top)
    lods = []
    if 16 in payloads:
        reader = Reader(payloads[16])
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
    embedded_lods = (_embedded_meshes(payloads[15]) if 15 in payloads else [])
    embedded_meshes = embedded_lods[0] if embedded_lods else []
    return Model(version=version, model_type=model_type, header=header,
                 lods=lods, skeleton_key=skeleton_key,
                 embedded_mesh=embedded_meshes[0] if embedded_meshes else b"",
                 embedded_meshes=embedded_meshes,
                 embedded_lods=embedded_lods,
                 embedded_skeleton=payloads.get(24, b""),
                 extra=[(ident, payload) for ident, payload in top
                        if ident not in (1, 15, 16, 20, 24)])
