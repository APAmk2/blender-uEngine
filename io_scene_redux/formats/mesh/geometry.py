from mathutils import Vector
from ...rw import common as binary
from ...utils import axis

def _packed_normal(value):
    raw = [(value >> (8 * i)) & 255 for i in range(3)]
    vector = Vector(tuple(2 * raw[i] / 255 - 1 for i in (2, 1, 0)))
    return vector.normalized() if vector.length else Vector((0, 0, 1))

def _encode_normal(normal, ao):
    n = Vector(normal).normalized()
    values = [max(0, min(255, round((n[i] + 1) * 127.5))) for i in (2, 1, 0)]
    return values[0] | values[1] << 8 | values[2] << 16 | (ao & 255) << 24


def _normals_per_vertex(mesh):
    """Read custom loop normals without silently losing skin vertex normals."""
    if hasattr(mesh, "calc_normals_split"):
        mesh.calc_normals_split()
    result = [None] * len(mesh.vertices)
    for loop in mesh.loops:
        normal = Vector(loop.normal)
        previous = result[loop.vertex_index]
        if previous is not None and (previous - normal).length > 0.03:
            raise binary.FormatError("Skin normal seam needs a split vertex; vertex count is fixed")
        result[loop.vertex_index] = normal
    return [normal if normal is not None else Vector(vertex.normal)
            for normal, vertex in zip(result, mesh.vertices)]

def _bind_position(vertex):
    """Packed positions are already in model-space bind pose."""
    return axis.to_blender_vector([x * 12.0 / 32767.0 for x in vertex.offset[:3]])


def _bind_normal(vertex):
    return axis.to_blender_vector(_packed_normal(vertex.normal))

