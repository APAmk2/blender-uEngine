import math
from array import array

from mathutils import Vector

from ...rw import mesh as binary
from ...utils import axis, bone as bone_utils
from ..common import (_active_uv_values, _selected_meshes, _source_bytes,
                      _mat_record, _uv_per_vertex, _triangles,
                      _bones_by_index)
from .geometry import _encode_normal, _normals_per_vertex


def _finite_vector(value):
    return all(math.isfinite(component) for component in value)


def _unit_vector(value, fallback):
    vector = Vector(value)
    if not _finite_vector(vector) or vector.length_squared <= 1e-20:
        return Vector(fallback)
    vector.normalize()
    return vector


def _fallback_tangent(normal):
    reference = Vector((0.0, 0.0, 1.0))
    if abs(normal.dot(reference)) > 0.9:
        reference = Vector((0.0, 1.0, 0.0))
    tangent = normal.cross(reference).normalized()
    return tangent, normal.cross(tangent).normalized()


def _loop_vectors(mesh, name):
    flat = array("f", [0.0]) * (len(mesh.loops) * 3)
    try:
        mesh.loops.foreach_get(name, flat)
        return [Vector((flat[index * 3], flat[index * 3 + 1],
                        flat[index * 3 + 2]))
                for index in range(len(mesh.loops))]
    except (AttributeError, IndexError, RuntimeError):
        try:
            return [Vector(getattr(loop, name)) for loop in mesh.loops]
        except (AttributeError, IndexError, RuntimeError):
            return None


def _loop_scalars(mesh, name):
    values = array("f", [0.0]) * len(mesh.loops)
    try:
        mesh.loops.foreach_get(name, values)
        return list(values)
    except (AttributeError, IndexError, RuntimeError):
        try:
            return [float(getattr(loop, name)) for loop in mesh.loops]
        except (AttributeError, IndexError, RuntimeError):
            return None


def _packed_influences(obj, vertex, bones, used_bones):
    if not bones:
        raise binary.FormatError(
            "Rebuilt skin mesh export requires its Redux armature")
    by_name = {bone.name: index for index, bone in bones.items()}
    influences = []
    for assignment in vertex.groups:
        weight = float(assignment.weight)
        if not math.isfinite(weight) or weight <= 0:
            continue
        group = obj.vertex_groups[assignment.group]
        bone_id = by_name.get(group.name)
        if bone_id is not None:
            influences.append((bone_id, weight))
    if not influences:
        raise binary.FormatError(
            "Skin vertex %d has no weights for the selected armature" %
            vertex.index)
    influences.sort(key=lambda item: item[1], reverse=True)
    influences = influences[:4]
    total = sum(weight for _bone, weight in influences)
    scaled = [weight * 255.0 / total for _bone, weight in influences]
    quantized = [math.floor(value) for value in scaled]
    remainder = 255 - sum(quantized)
    order = sorted(range(len(scaled)),
                   key=lambda index: scaled[index] - quantized[index],
                   reverse=True)
    for index in order[:remainder]:
        quantized[index] += 1
    result = [(bone_id, weight)
              for (bone_id, _source), weight
              in zip(influences, quantized) if weight]
    for bone_id, _weight in result:
        if bone_id not in used_bones:
            used_bones.append(bone_id)
    return result


def _mark_open_edges(vertices, faces):
    edge_uses = {}
    for face in faces:
        for first, second in ((face[0], face[1]),
                              (face[1], face[2]),
                              (face[2], face[0])):
            edge = (first, second) if first < second else (second, first)
            edge_uses[edge] = edge_uses.get(edge, 0) + 1
    marked = set()
    for edge, uses in edge_uses.items():
        if uses != 2:
            marked.update(edge)
    for index in marked:
        vertices[index].tangent |= 0xff000000


def _rebuild_topology(obj, mesh, old, bones):
    if not old.vertices or old.vertices[0].modern or old.auxiliary or old.lods:
        raise binary.FormatError(
            "This packed skin layout requires exact source vertex topology")
    if not math.isfinite(old.scale) or old.scale == 0:
        raise binary.FormatError("Skin position scale is invalid")
    mesh.calc_loop_triangles()
    if hasattr(mesh, "calc_normals_split"):
        mesh.calc_normals_split()
    uv_values = _active_uv_values(mesh)
    if uv_values is None:
        raise binary.FormatError(
            "Mesh has no readable active UV map; UV coordinates cannot be exported")
    have_tangents = False
    if hasattr(mesh, "calc_tangents"):
        try:
            mesh.calc_tangents(uvmap=mesh.uv_layers.active.name)
            have_tangents = True
        except (IndexError, RuntimeError):
            pass
    normals = _loop_vectors(mesh, "normal")
    if normals is None:
        raise binary.FormatError("Mesh loop normals cannot be read")
    tangents = _loop_vectors(mesh, "tangent") if have_tangents else None
    signs = _loop_scalars(mesh, "bitangent_sign") if have_tangents else None
    have_tangents = tangents is not None and signs is not None

    used_bones = list(old.used_bones)
    influence_cache = {}
    vertices = []
    faces = []
    mapping = {}
    for triangle in mesh.loop_triangles:
        face = []
        for loop_index in triangle.loops:
            loop = mesh.loops[loop_index]
            source = mesh.vertices[loop.vertex_index]
            if source.index not in influence_cache:
                influence_cache[source.index] = _packed_influences(
                    obj, source, bones, used_bones)
            influences = influence_cache[source.index]

            point = axis.to_redux_vector(source.co)
            if not _finite_vector(point):
                raise binary.FormatError(
                    "Skin vertex %d has a non-finite position" % source.index)
            raw_point = tuple(
                max(-32768, min(32767,
                    round(component * 32768 / old.scale)))
                for component in point)

            uv = uv_values[loop_index]
            uv = (uv[0], 1.0 - uv[1])
            if not _finite_vector(uv):
                raise binary.FormatError(
                    "Mesh UV corner %d contains a non-finite value" % loop_index)
            raw_uv = tuple(
                max(-32768, min(32767, round(component * 2048)))
                for component in uv)

            normal_value = _unit_vector(normals[loop_index], (0.0, 0.0, 1.0))
            if have_tangents:
                tangent_value = Vector(tangents[loop_index])
                tangent_value -= normal_value * normal_value.dot(tangent_value)
                sign = signs[loop_index]
                if (not _finite_vector(tangent_value) or
                        tangent_value.length_squared <= 1e-20 or
                        not math.isfinite(sign)):
                    tangent_value, binormal_value = _fallback_tangent(normal_value)
                else:
                    tangent_value.normalize()
                    fallback = _fallback_tangent(normal_value)[1]
                    binormal_value = _unit_vector(
                        normal_value.cross(tangent_value) * sign, fallback)
            else:
                tangent_value, binormal_value = _fallback_tangent(normal_value)

            normal = _encode_normal(axis.to_redux_vector(normal_value), 255)
            tangent = _encode_normal(axis.to_redux_vector(tangent_value), 0)
            binormal = _encode_normal(axis.to_redux_vector(binormal_value), 0)
            packed_bones = 0
            packed_weights = 0
            for influence_index, (bone_id, weight) in enumerate(influences):
                used_index = used_bones.index(bone_id)
                packed_index = (used_index if old.vertices[0].direct_bones
                                else used_index * 3)
                if packed_index > 255:
                    raise binary.FormatError(
                        "Skin uses too many bones for packed vertex indices")
                slot = (2, 1, 0, 3)[influence_index]
                packed_bones |= packed_index << (8 * slot)
                packed_weights |= weight << (8 * slot)
            packed = binary.SkinVertex(
                raw_point + (len(influences),), normal, tangent, binormal,
                packed_bones, packed_weights, raw_uv, False,
                old.vertices[0].direct_bones)
            key = (packed.offset, packed.normal, packed.tangent,
                   packed.binormal, packed.bones, packed.weights, packed.uv)
            index = mapping.get(key)
            if index is None:
                index = len(vertices)
                mapping[key] = index
                vertices.append(packed)
            face.append(index)
        faces.append((face[0], face[2], face[1]))
    if len(vertices) > 65535:
        raise binary.FormatError(
            "Rebuilt skin exceeds the 65535 packed vertex limit")
    _mark_open_edges(vertices, faces)
    return vertices, faces, used_bones


def _source_topology(obj, mesh, old, armature, bones):
    if not math.isfinite(old.scale) or old.scale == 0:
        raise binary.FormatError("Skin position scale is invalid")
    if len(mesh.vertices) != len(old.vertices):
        raise binary.FormatError(
            "Skin vertex count changed; this packed layout requires exact topology")
    uv = _uv_per_vertex(mesh)
    normals = _normals_per_vertex(mesh)
    vertices = []
    for index, vertex in enumerate(mesh.vertices):
        packed = old.vertices[index]
        if armature and any(
                bone_id not in bones for bone_id, _weight
                in packed.influences(old.used_bones)):
            raise binary.FormatError(
                "Skin bone index exceeds selected armature")
        point = axis.to_redux_vector(vertex.co)
        if not _finite_vector(point):
            raise binary.FormatError(
                "Skin vertex %d has a non-finite position" % vertex.index)
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
    faces = [(face[0], face[2], face[1]) for face in _triangles(mesh)]
    return vertices, faces, list(old.used_bones)


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
        if getattr(obj, "mode", "OBJECT") == "EDIT" and hasattr(obj, "update_from_editmode"):
            obj.update_from_editmode()
        mesh = obj.data
        armature = next((modifier.object for modifier in obj.modifiers
                         if modifier.type == "ARMATURE" and modifier.object),
                        None)
        if armature and armature.get("redux_axis_basis") != axis.BASIS_ID:
            raise binary.FormatError(
                "Reimport the mesh's armature with the current Redux axis conversion")
        bones = _bones_by_index(armature) if armature else {}
        rebuild = bool(obj.get("redux_rebuild_vertices"))
        if rebuild:
            vertices, faces, used_bones = _rebuild_topology(
                obj, mesh, old, bones)
        else:
            vertices, faces, used_bones = _source_topology(
                obj, mesh, old, armature, bones)

        material = mesh.materials[0] if mesh.materials else None
        record = _mat_record(material, old.material.name)
        part_header = binary.bounds_header(
            [tuple(component * old.scale / 32768
                   for component in vertex.offset[:3])
             for vertex in vertices],
            5, old.header)
        boxes = old.bone_boxes
        if recompute_bone_boxes or used_bones != old.used_bones:
            generated = bytearray()
            for bone_id in used_bones:
                points = [
                    tuple(component * old.scale / 32768
                          for component in vertex.offset[:3])
                    for vertex in vertices
                    if any(index == bone_id for index, _weight
                           in vertex.influences(used_bones))]
                generated += bone_utils.generate_obb(points)
            boxes = bytes(generated)
        shadow_faces = [] if rebuild else old.shadow_faces
        parts.append(binary.SkinPart(
            record, used_bones, boxes, vertices, faces,
            shadow_faces, part_header, old.extra, old.scale,
            old.auxiliary, old.lods, old.selected_lod))
    positions = [
        tuple(component * part.scale / 32768
              for component in vertex.offset[:3])
        for part in parts for vertex in part.vertices]
    outer_header = binary.bounds_header(positions, 4, original.header)
    return binary.write_mesh(binary.SkinModel(
        parts, original.bones_crc, outer_header, original.extra))


export_data = _export_mesh
