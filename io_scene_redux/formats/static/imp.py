from pathlib import Path
from ...rw import static as binary
from ...utils import axis
from ..common import _mesh_object, _store_source


def _weld_part(part):
    """Turn split render vertices into Blender vertices and corner data."""
    mapping = {}
    positions = []
    source_to_welded = []
    for vertex in part.vertices:
        key = tuple(vertex[0])
        index = mapping.get(key)
        if index is None:
            index = len(positions)
            mapping[key] = index
            positions.append(axis.to_blender_static_vector(vertex[0]))
        source_to_welded.append(index)

    faces = []
    corner_records = []
    for face in part.faces:
        source_face = (face[0], face[2], face[1])
        welded_face = tuple(source_to_welded[index] for index in source_face)
        if len(set(welded_face)) != 3:
            # Some assets pad a part with (0, 0, 0) triangles. They have no
            # surface and Blender cannot represent them as polygons.
            continue
        faces.append(welded_face)
        corner_records.extend(source_face)
    return positions, faces, corner_records


def import_data(context, path, data, expected_type=10, source_name=None):
    model = binary.read_static(data, expected_type=expected_type)
    source_text = _store_source(source_name or Path(path).name, data)
    for number, part in enumerate(model.parts):
        hidden = bool(part.material.flags & 0x0008)
        name = "%s_%02d" % (Path(path).name, number)
        if hidden:
            reason = ("collision" if "collision" in part.material.name.lower()
                      else "no_render")
            name += "_" + reason
        if expected_type == 1:
            positions, faces, corner_records = _weld_part(part)
        else:
            positions = [axis.to_blender_static_vector(v[0]) for v in part.vertices]
            faces = [(face[0], face[2], face[1]) for face in part.faces]
            corner_records = None
        obj = _mesh_object(context, path, name,
                           positions, faces,
                           [axis.to_blender_static_vector(v[1]) for v in part.vertices],
                           [v[2] for v in part.vertices], part.material,
                           positions_in_blender=True, normals_in_blender=True,
                           flags_schema="static_part",
                           corner_records=corner_records)
        obj["redux_format"] = "static"
        obj["redux_axis_basis"] = axis.STATIC_BASIS_ID
        obj["redux_source_text"] = source_text
        obj["redux_part"] = number
        obj["redux_source_vertex_count"] = len(part.vertices)
        if hidden:
            obj["redux_no_render"] = True
            obj.hide_render = True
            obj.hide_set(True)
    return len(model.parts)


def import_path(context, path):
    return import_data(context, path, Path(path).read_bytes())
