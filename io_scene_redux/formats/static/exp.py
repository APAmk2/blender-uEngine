from ...rw import static as binary
from ...utils import axis, mesh as mesh_utils
from ..common import _selected_meshes, _source_bytes, _mat_record


def _parts_from_mesh(obj, mesh, old):
    mesh.calc_loop_triangles()
    if hasattr(mesh, "calc_normals_split"):
        mesh.calc_normals_split()
    parts = []
    material_indices = sorted({tri.material_index for tri in mesh.loop_triangles})
    for material_index in material_indices:
        mat = mesh.materials[material_index] if material_index < len(mesh.materials) else None
        record = _mat_record(mat, obj.name)
        if old and material_index == 0:
            record.lmd = float(mat.get("redux_lmd", old.material.lmd)) if mat else old.material.lmd
        vertices = []
        vertex_basis = []
        faces = []
        mapping = {}
        for tri in mesh.loop_triangles:
            if tri.material_index != material_index:
                continue
            face = []
            for loop_index in tri.loops:
                loop = mesh.loops[loop_index]
                vertex = mesh.vertices[loop.vertex_index]
                uv = (0.0, 0.0)
                if mesh.uv_layers.active:
                    uv_value = mesh.uv_layers.active.data[loop_index].uv
                    uv = (uv_value.x, 1.0 - uv_value.y)
                normal = tuple(axis.to_redux_static_vector(loop.normal))
                key = (vertex.index, uv, normal)
                if key not in mapping:
                    mapping[key] = len(vertices)
                    color = (old.vertices[vertex.index][3]
                             if old and vertex.index < len(old.vertices) else 0x00ffffff)
                    vertices.append((tuple(axis.to_redux_static_vector(vertex.co)), normal, uv, color))
                    vertex_basis.append(old.vertex_basis[vertex.index]
                                        if old and vertex.index < len(old.vertex_basis)
                                        else None)
                face.append(mapping[key])
            faces.append((face[0], face[2], face[1]))
        extra = old.extra if old and material_index == 0 else []
        parts.append(binary.StaticPart(record, vertices, faces, extra, vertex_basis))
    return parts


def export_data(context, apply_modifiers=False, apply_transform=True):
    objects = _selected_meshes(context)
    source = objects[0].get("redux_source_text")
    original = (binary.read_static(_source_bytes(objects[0]))
                if source and objects[0].get("redux_format") == "static" else None)
    if original and any(obj.get("redux_source_text") != source for obj in objects):
        raise binary.FormatError("Select parts from one Redux static source")
    parts = []
    for obj in objects:
        if obj.get("redux_format") == "static" and obj.get("redux_axis_basis") != axis.STATIC_BASIS_ID:
            raise binary.FormatError("Reimport this static with the current Redux axis conversion")
        number = int(obj.get("redux_part", -1))
        old = original.parts[number] if original and 0 <= number < len(original.parts) else None
        with mesh_utils.export_mesh_data(obj, context, apply_modifiers, apply_transform) as mesh:
            parts.extend(_parts_from_mesh(obj, mesh, old))
    model = binary.StaticModel(parts, original.header if original else b"",
                               original.guid if original else bytes(16),
                               original.extra if original else [])
    if original:
        positions = [vertex[0] for part in parts for vertex in part.vertices]
        model.header = binary.bounds_header(positions, 10, original.header)
    return binary.write_static(model)
