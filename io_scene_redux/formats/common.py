import base64
from array import array
from pathlib import Path
import bpy
from ..rw import common as binary
from ..utils import axis, material as material_utils, tex, version

def _material(context, source_path, name, record, flags_schema=None):
    mat = material_utils.find_material(record, flags_schema)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat["redux_texture"] = record.texture
        mat["redux_shader"] = record.shader
        mat["redux_game_material"] = record.game_material
        mat["redux_flags"] = record.flags
        if flags_schema:
            mat["redux_flags_schema"] = flags_schema
        mat["redux_lmd"] = record.lmd
        mat["redux_part_name"] = record.name
    addon = context.preferences.addons.get("io_scene_redux")
    if record.texture and (addon is None or addon.preferences.load_textures):
        root = _content_root(context, source_path)
        if root:
            try:
                image, image_path = tex.load_texture_image(root, record.texture)
                if image:
                    mat.use_nodes = True
                    nodes = mat.node_tree.nodes
                    principled = next((node for node in nodes if node.type == "BSDF_PRINCIPLED"), None)
                    if principled:
                        texture_node = next((node for node in nodes if node.type == "TEX_IMAGE"), None)
                        if texture_node is None:
                            texture_node = nodes.new("ShaderNodeTexImage")
                        texture_node.image = image
                        texture_node.location = (principled.location.x - 300, principled.location.y)
                        mat.node_tree.links.new(texture_node.outputs["Color"], principled.inputs["Base Color"])
                        mat["redux_texture_file"] = str(image_path)
                        mat["redux_texture_status"] = "Loaded"
                else:
                    mat["redux_texture_status"] = "Source image not found or unsupported"
            except ValueError:
                mat["redux_texture_status"] = "Invalid texture path"
        else:
            mat["redux_texture_status"] = "Set SDK content directory in add-on preferences"
    elif record.texture:
        mat["redux_texture_status"] = "Loading disabled in add-on preferences"
    return mat

def _texture_name(mat):
    if mat is None:
        return ""
    value = mat.get("redux_texture", "")
    if value:
        return value
    candidates = [mat.get("redux_texture_file", "")]
    if mat.use_nodes and mat.node_tree:
        candidates.extend(
            node.image.filepath for node in mat.node_tree.nodes
            if node.type == "TEX_IMAGE" and node.image and node.image.filepath)
    for value in candidates:
        if not value:
            continue
        path = Path(bpy.path.abspath(value))
        parts = path.parts
        for index in range(len(parts) - 1, -1, -1):
            if parts[index].lower() == "textures" and index + 1 < len(parts):
                relative = Path(*parts[index + 1:]).with_suffix("")
                return str(relative).replace("/", "\\")
    return ""


def _mat_record(mat, default_name):
    return binary.Material(
        _texture_name(mat),
        mat.get("redux_shader", "geometry\\default") if mat else "geometry\\default",
        mat.get("redux_game_material", "default") if mat else "default",
        mat.get("redux_part_name", default_name) if mat else default_name,
        int(mat.get("redux_flags", 0)) if mat else 0,
        float(mat.get("redux_lmd", 1.0)) if mat else 1.0,
    )

def _mesh_object(context, source_path, name, positions, faces, normals, uvs, material,
                 positions_in_blender=False, normals_in_blender=False,
                 flags_schema=None, corner_records=None):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata((positions if positions_in_blender else
                      [axis.to_blender_vector(p) for p in positions]), [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj["redux_axis_basis"] = axis.BASIS_ID
    version.link_object(obj, context)
    mesh.materials.append(_material(context, source_path, material.name or name, material,
                                    flags_schema))
    mesh.materials[0]["redux_part_name"] = material.name
    uv_layer = mesh.uv_layers.new(name="Redux UV")
    loop_normals = [None] * len(mesh.loops)
    for poly in mesh.polygons:
        poly.use_smooth = True
        for loop_index in poly.loop_indices:
            loop = mesh.loops[loop_index]
            i = (corner_records[loop_index] if corner_records is not None else
                 loop.vertex_index)
            uv_layer.data[loop_index].uv = (uvs[i][0], 1.0 - uvs[i][1])
            loop_normals[loop_index] = (normals[i] if normals_in_blender else
                                        axis.to_blender_vector(normals[i]))
    # Set custom split normals only after mesh topology exists.
    if hasattr(mesh, "normals_split_custom_set"):
        if hasattr(mesh, "use_auto_smooth"):
            mesh.use_auto_smooth = True
        mesh.normals_split_custom_set(loop_normals)
    return obj

def _store_source(name, data):
    """Keep one copy per imported file inside the .blend for later export."""
    block = bpy.data.texts.new("Redux source: " + name)
    encoded = base64.b64encode(data).decode("ascii")
    # A single multi-megabyte Text line makes Blender's Text.write quadratic.
    block.from_string("\n".join(encoded[i:i + 4096]
                                for i in range(0, len(encoded), 4096)))
    return block.name

def _source_bytes(obj):
    block_name = obj.get("redux_source_text")
    if not block_name:
        raise binary.FormatError("Original Redux source data is missing")
    block = bpy.data.texts.get(block_name)
    if block is None:
        raise binary.FormatError("Redux source text block %r is missing" % block_name)
    try:
        # Older imports used one line; current imports wrap long sources.
        return base64.b64decode("".join(block.as_string().splitlines()), validate=True)
    except ValueError as exc:
        raise binary.FormatError("Invalid saved Redux source data") from exc

def _active_armature(context, crc, skeleton_key=None):
    def matches(obj):
        if obj.get("redux_axis_basis") != axis.BASIS_ID:
            return False
        if skeleton_key and obj.get("redux_skeleton_key", "").lower() != skeleton_key.lower():
            return False
        value = obj.get("redux_bones_crc")
        if value is None:
            return False
        return (int(value, 16) if isinstance(value, str) else int(value) & 0xffffffff) == crc

    obj = context.active_object
    if obj and obj.type == "ARMATURE" and matches(obj):
        return obj
    return next((o for o in context.scene.objects if o.type == "ARMATURE" and matches(o)), None)

def _bones_by_index(armature):
    return {int(bone.get("redux_index", index)): bone
            for index, bone in enumerate(armature.data.bones)}

def _content_root(context, source_path):
    addon = context.preferences.addons.get("io_scene_redux")
    if addon and addon.preferences.content_root:
        return Path(bpy.path.abspath(addon.preferences.content_root))
    for parent in Path(source_path).resolve().parents:
        if parent.name.lower() == "content":
            return parent
    return None

def _triangles(mesh):
    mesh.calc_loop_triangles()
    return [tuple(tri.vertices) for tri in mesh.loop_triangles]

def _active_uv_values(mesh):
    layer = mesh.uv_layers.active
    if layer is None or len(layer.data) != len(mesh.loops):
        return None
    flat = array("f", [0.0]) * (len(mesh.loops) * 2)
    try:
        layer.data.foreach_get("uv", flat)
        return [(flat[index * 2], flat[index * 2 + 1])
                for index in range(len(mesh.loops))]
    except (AttributeError, IndexError, RuntimeError):
        try:
            return [(item.uv.x, item.uv.y) for item in layer.data]
        except (IndexError, RuntimeError):
            return None

def _uv_per_vertex(mesh):
    result = [(0.0, 0.0)] * len(mesh.vertices)
    values = _active_uv_values(mesh)
    if values is not None:
        seen = {}
        for loop in mesh.loops:
            uv = values[loop.index]
            value = (uv[0], 1.0 - uv[1])
            prior = seen.get(loop.vertex_index)
            if prior is not None and any(abs(a - b) > 1e-5 for a, b in zip(prior, value)):
                raise binary.FormatError("Skin UV seam needs a split vertex; vertex count is fixed")
            seen[loop.vertex_index] = value
            result[loop.vertex_index] = value
    return result

def _selected_meshes(context):
    result = [o for o in context.selected_objects if o.type == "MESH"]
    if not result:
        raise binary.FormatError("Select one or more mesh objects")
    return sorted(result, key=lambda o: int(o.get("redux_part", 9999)))

