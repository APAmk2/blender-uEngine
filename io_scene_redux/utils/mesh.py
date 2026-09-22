import math
from contextlib import contextmanager


def calculate_mesh_bbox(positions):
    if not positions:
        raise ValueError("Cannot calculate bounds of an empty mesh")
    minimum = tuple(min(position[axis] for position in positions) for axis in range(3))
    maximum = tuple(max(position[axis] for position in positions) for axis in range(3))
    return minimum, maximum


def calculate_mesh_bsphere(bbox, positions):
    center = tuple((a + b) * 0.5 for a, b in zip(*bbox))
    radius = max(math.dist(center, position) for position in positions)
    return center, radius


@contextmanager
def export_mesh_data(obj, context, apply_modifiers=False, apply_transform=True):
    """Export from a temporary mesh, leaving the Blender object untouched."""
    import bpy
    if apply_modifiers:
        depsgraph = context.evaluated_depsgraph_get()
        evaluated = obj.evaluated_get(depsgraph)
        mesh = bpy.data.meshes.new_from_object(
            evaluated, preserve_all_data_layers=True, depsgraph=depsgraph)
    else:
        mesh = obj.data.copy()
    try:
        if apply_transform:
            mesh.transform(obj.matrix_world)
            mesh.update()
        yield mesh
    finally:
        bpy.data.meshes.remove(mesh)
