from ...rw import mesh as binary
from ...utils import axis, bone as bone_utils
from ..common import _selected_meshes, _source_bytes, _mat_record, _uv_per_vertex, _triangles, _bones_by_index
from .geometry import _encode_normal, _normals_per_vertex

def _export_mesh(context, recompute_bone_boxes=False):
    objects = _selected_meshes(context)
    source = objects[0].get("redux_source_text")
    if not source or any(o.get("redux_source_text") != source or o.get("redux_format") != "mesh" for o in objects):
        raise binary.FormatError("Mesh export requires parts imported from the same Redux .mesh")
    original = binary.read_mesh(_source_bytes(objects[0]))
    parts = []
    for obj in objects:
        if obj.get("redux_axis_basis") != axis.BASIS_ID:
            raise binary.FormatError("Reimport this mesh with the current Redux axis conversion")
        number = int(obj.get("redux_part", -1))
        if not 0 <= number < len(original.parts):
            raise binary.FormatError("Invalid imported part number")
        old = original.parts[number]
        mesh = obj.data
        if len(mesh.vertices) != len(old.vertices):
            raise binary.FormatError("Skin vertex count changed; packed skin data cannot be reassigned")
        uv = _uv_per_vertex(mesh)
        normals = _normals_per_vertex(mesh)
        armature = next((m.object for m in obj.modifiers if m.type == "ARMATURE" and m.object), None)
        if armature and armature.get("redux_axis_basis") != axis.BASIS_ID:
            raise binary.FormatError("Reimport the mesh's armature with the current Redux axis conversion")
        bones = _bones_by_index(armature) if armature else {}
        vertices = []
        for index, v in enumerate(mesh.vertices):
            packed = old.vertices[index]
            if armature and any(bone_id not in bones for bone_id, _weight
                               in packed.influences(old.used_bones)):
                raise binary.FormatError("Skin bone index exceeds selected armature")
            point = axis.to_redux_vector(v.co)
            offset = tuple(max(-32768, min(32767, round(c * 32767 / 12))) for c in point)
            offset += (packed.offset[3],)
            raw_uv = tuple(max(-32768, min(32767, round(c * 2048))) for c in uv[index])
            normal = _encode_normal(axis.to_redux_vector(normals[index]), packed.normal >> 24)
            vertices.append(binary.SkinVertex(offset, normal, packed.tangent, packed.binormal,
                                               packed.bones, packed.weights, raw_uv))
        mat = mesh.materials[0] if mesh.materials else None
        record = _mat_record(mat, old.material.name)
        part_header = binary.bounds_header(
            [tuple(c * 12 / 32767 for c in v.offset[:3]) for v in vertices],
            5, old.header)
        boxes = old.bone_boxes
        if recompute_bone_boxes:
            generated = bytearray()
            for bone_id in old.used_bones:
                points = [tuple(c * 12 / 32767 for c in vertex.offset[:3])
                          for vertex in vertices
                          if any(index == bone_id for index, _weight
                                 in vertex.influences(old.used_bones))]
                generated += bone_utils.generate_obb(points)
            boxes = bytes(generated)
        parts.append(binary.SkinPart(record, old.used_bones,
                                     boxes, vertices, _triangles(mesh),
                                     old.shadow_faces, part_header, old.extra))
    positions = [tuple(c * 12 / 32767 for c in v.offset[:3])
                 for part in parts for v in part.vertices]
    outer_header = binary.bounds_header(positions, 4, original.header)
    return binary.write_mesh(binary.SkinModel(parts, original.bones_crc,
                                               outer_header, original.extra))


export_data = _export_mesh

