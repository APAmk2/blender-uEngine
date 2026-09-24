from ...rw import mesh as binary
from ...utils import axis, bone as bone_utils
from ..common import (_selected_meshes, _source_bytes, _mat_record,
                      _uv_per_vertex, _triangles, _bones_by_index)
from .geometry import _encode_normal, _normals_per_vertex


def _export_mesh(context, recompute_bone_boxes=False):
    objects = _selected_meshes(context)
    source = objects[0].get("redux_source_text")
    if not source or any(
            obj.get("redux_source_text") != source or
            obj.get("redux_format") != "mesh" for obj in objects):
        raise binary.FormatError(
            "Mesh export requires parts imported from the same Redux .mesh")
    original = binary.read_mesh(_source_bytes(objects[0]))
    parts = []
    for obj in objects:
        if obj.get("redux_axis_basis") != axis.BASIS_ID:
            raise binary.FormatError(
                "Reimport this mesh with the current Redux axis conversion")
        number = int(obj.get("redux_part", -1))
        if not 0 <= number < len(original.parts):
            raise binary.FormatError("Invalid imported part number")
        old = original.parts[number]
        mesh = obj.data
        if len(mesh.vertices) != len(old.vertices):
            raise binary.FormatError(
                "Skin vertex count changed; packed skin data cannot be reassigned")
        uv = _uv_per_vertex(mesh)
        normals = _normals_per_vertex(mesh)
        armature = next((modifier.object for modifier in obj.modifiers
                         if modifier.type == "ARMATURE" and modifier.object),
                        None)
        if armature and armature.get("redux_axis_basis") != axis.BASIS_ID:
            raise binary.FormatError(
                "Reimport the mesh's armature with the current Redux axis conversion")
        bones = _bones_by_index(armature) if armature else {}
        vertices = []
        for index, vertex in enumerate(mesh.vertices):
            packed = old.vertices[index]
            if armature and any(
                    bone_id not in bones for bone_id, _weight
                    in packed.influences(old.used_bones)):
                raise binary.FormatError(
                    "Skin bone index exceeds selected armature")
            point = axis.to_redux_vector(vertex.co)
            offset = tuple(
                max(-32768, min(32767,
                    round(component * 32768 / old.scale)))
                for component in point)
            offset += (packed.offset[3],)
            if packed.modern:
                low_uv = ((packed.tangent & 0xff) & 0x0f,
                          (packed.tangent >> 4) & 0xff)
                raw_uv = tuple(
                    max(-32768, min(32767,
                        round(component * 2048 - low / 16)))
                    for component, low in zip(uv[index], low_uv))
            else:
                raw_uv = tuple(
                    max(-32768, min(32767, round(component * 2048)))
                    for component in uv[index])
            normal = _encode_normal(
                axis.to_redux_vector(normals[index]), packed.normal >> 24)
            vertices.append(binary.SkinVertex(
                offset, normal, packed.tangent, packed.binormal,
                packed.bones, packed.weights, raw_uv,
                packed.modern, packed.direct_bones))
        material = mesh.materials[0] if mesh.materials else None
        record = _mat_record(material, old.material.name)
        part_header = binary.bounds_header(
            [tuple(component * old.scale / 32768
                   for component in vertex.offset[:3])
             for vertex in vertices],
            5, old.header)
        boxes = old.bone_boxes
        if recompute_bone_boxes:
            generated = bytearray()
            for bone_id in old.used_bones:
                points = [
                    tuple(component * old.scale / 32768
                          for component in vertex.offset[:3])
                    for vertex in vertices
                    if any(index == bone_id for index, _weight
                           in vertex.influences(old.used_bones))]
                generated += bone_utils.generate_obb(points)
            boxes = bytes(generated)
        parts.append(binary.SkinPart(
            record, old.used_bones, boxes, vertices, _triangles(mesh),
            old.shadow_faces, part_header, old.extra, old.scale,
            old.auxiliary, old.lods, old.selected_lod))
    positions = [
        tuple(component * part.scale / 32768
              for component in vertex.offset[:3])
        for part in parts for vertex in part.vertices]
    outer_header = binary.bounds_header(positions, 4, original.header)
    return binary.write_mesh(binary.SkinModel(
        parts, original.bones_crc, outer_header, original.extra))


export_data = _export_mesh
