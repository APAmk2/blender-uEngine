from pathlib import Path
from ...rw import static as binary
from ...utils import axis
from ..common import _mesh_object, _store_source


def import_data(context, path, data, expected_type=10, source_name=None):
    model = binary.read_static(data, expected_type=expected_type)
    source_text = _store_source(source_name or Path(path).name, data)
    for number, part in enumerate(model.parts):
        obj = _mesh_object(context, path, "%s_%02d" % (Path(path).name, number),
                           [axis.to_blender_static_vector(v[0]) for v in part.vertices],
                           [(face[0], face[2], face[1]) for face in part.faces],
                           [axis.to_blender_static_vector(v[1]) for v in part.vertices],
                           [v[2] for v in part.vertices], part.material,
                           positions_in_blender=True, normals_in_blender=True,
                           flags_schema="static_part")
        obj["redux_format"] = "static"
        obj["redux_axis_basis"] = axis.STATIC_BASIS_ID
        obj["redux_source_text"] = source_text
        obj["redux_part"] = number
    return len(model.parts)


def import_path(context, path):
    return import_data(context, path, Path(path).read_bytes())
