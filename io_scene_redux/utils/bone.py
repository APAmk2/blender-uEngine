import struct


IDENTITY_BOX = struct.pack("<15f", 1, 0, 0, 0, 1, 0, 0, 0, 1,
                           0, 0, 0, 0, 0, 0)


def generate_obb(points):
    """Return Redux Obb60 for points in one bone's local space."""
    if not points:
        return IDENTITY_BOX
    try:
        import numpy
        array = numpy.asarray(points, dtype=numpy.float64)
        if len(points) >= 3:
            covariance = numpy.cov(array, rowvar=False, bias=True)
            _values, basis = numpy.linalg.eigh(covariance)
        else:
            basis = numpy.eye(3)
        aligned = array @ basis
        low = aligned.min(axis=0)
        high = aligned.max(axis=0)
        center = ((low + high) * 0.5) @ basis.T
        halfsize = (high - low) * 0.5
        return struct.pack("<15f", *basis[:, 0], *basis[:, 1], *basis[:, 2],
                           *center, *halfsize)
    except (ImportError, ValueError):
        minimum = [min(point[axis] for point in points) for axis in range(3)]
        maximum = [max(point[axis] for point in points) for axis in range(3)]
        center = [(a + b) * 0.5 for a, b in zip(minimum, maximum)]
        halfsize = [(b - a) * 0.5 for a, b in zip(minimum, maximum)]
        return struct.pack("<15f", 1, 0, 0, 0, 1, 0, 0, 0, 1,
                           *center, *halfsize)
