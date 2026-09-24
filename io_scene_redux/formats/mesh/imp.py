from pathlib import Path
from ...rw import mesh as binary
from ..common import _active_armature, _bones_by_index, _mesh_object, _store_source
from ..skeleton.imp import _load_matching_skeleton, _skeleton_key_for_mesh
from .geometry import _bind_normal, _bind_position


def _can_rebuild(part):
    return (bool(part.vertices) and not part.vertices[0].modern and
            not part.auxiliary and not part.lods)


def _weld_part(part):
    mapping = {}
    positions = []
    influences = []
    source_to_welded = []
    for vertex in part.vertices:
        vertex_influences = tuple(vertex.influences(part.used_bones))
        key = (vertex.offset[:3], vertex_influences)
        index = mapping.get(key)
        if index is None:
            index = len(positions)
            mapping[key] = index
            positions.append(_bind_position(vertex, part.scale))
            influences.append(vertex_influences)
        source_to_welded.append(index)
    faces = [(source_to_welded[face[0]], source_to_welded[face[2]],
              source_to_welded[face[1]]) for face in part.faces]
    corner_records = [index for face in part.faces
                      for index in (face[0], face[2], face[1])]
    return positions, faces, corner_records, influences


def import_data(context, path, data, skeleton_key=None, source_name=None,
                geometry_data=None):
    model = binary.read_mesh(data, geometry_data)
    if skeleton_key is None:
        skeleton_key = _skeleton_key_for_mesh(context, path, model.bones_crc)
    armature = _active_armature(context, model.bones_crc, skeleton_key)
    if armature is None:
        armature = _load_matching_skeleton(context, path, model.bones_crc, skeleton_key)
    bones = _bones_by_index(armature) if armature else {}
    source_text = _store_source(source_name or Path(path).name, data)
    for number, part in enumerate(model.parts):
        rebuild = _can_rebuild(part)
        if rebuild:
            positions, faces, corner_records, influences = _weld_part(part)
        else:
            positions = [_bind_position(v, part.scale) for v in part.vertices]
            faces = [(face[0], face[2], face[1]) for face in part.faces]
            corner_records = None
            influences = [vertex.influences(part.used_bones)
                          for vertex in part.vertices]
        obj = _mesh_object(context, path, "%s_%02d" % (Path(path).name, number),
                           positions, faces,
                           [_bind_normal(v) for v in part.vertices],
                           [v.texcoord() for v in part.vertices],
                           part.material, positions_in_blender=True,
                           normals_in_blender=True, flags_schema="edit_material",
                           corner_records=corner_records)
        obj["redux_format"] = "mesh"
        obj["redux_rebuild_vertices"] = rebuild
        obj["redux_source_text"] = source_text
        obj["redux_part"] = number
        obj["redux_bones_crc"] = "%08X" % model.bones_crc
        if armature:
            for index, vertex_influences in enumerate(influences):
                for bone_id, weight in vertex_influences:
                    group_name = bones[bone_id].name
                    group = obj.vertex_groups.get(group_name) or obj.vertex_groups.new(name=group_name)
                    group.add([index], weight, "REPLACE")
            modifier = obj.modifiers.new("Redux skin", "ARMATURE")
            modifier.object = armature
            obj.parent = armature
    return len(model.parts)


def import_path(context, path, skeleton_key=None):
    return import_data(context, path, Path(path).read_bytes(), skeleton_key)
