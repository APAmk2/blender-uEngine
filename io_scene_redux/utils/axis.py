"""Convert between uEngine's left-handed Y-up basis and Blender."""

from mathutils import Matrix, Vector


BASIS_ID = "X_Z_Y"
STATIC_BASIS_ID = "X_Z_Y"


def to_blender_basis():
    return Matrix(((1, 0, 0, 0),
                   (0, 0, 1, 0),
                   (0, 1, 0, 0),
                   (0, 0, 0, 1)))


def to_blender_vector(value):
    return Vector((value[0], value[2], value[1]))


def to_redux_vector(value):
    return Vector((value[0], value[2], value[1]))


def to_blender_static_vector(value):
    """Map static level X/Z to Blender top-view X/Y."""
    return Vector((value[0], value[2], value[1]))


def to_redux_static_vector(value):
    return Vector((value[0], value[2], value[1]))


def to_blender_matrix(value):
    basis = to_blender_basis()
    return basis @ value @ basis.transposed()


def to_redux_matrix(value):
    basis = to_blender_basis()
    return basis.transposed() @ value @ basis
