"""Small 4x4 matrix helpers for transform math without Maya.

Matrices are nested lists in row-vector convention, the same convention
Maya's MMatrix and USD's GfMatrix4d use: a point is transformed as
``p * M``. Only what the checks and the publisher need lives here:
composing translate/rotate/scale, multiplying and transforming points.

"""

import math

IDENTITY = (
    (1.0, 0.0, 0.0, 0.0),
    (0.0, 1.0, 0.0, 0.0),
    (0.0, 0.0, 1.0, 0.0),
    (0.0, 0.0, 0.0, 1.0),
)


def identity():
    """Return a fresh identity matrix.

    Returns:
        list: 4x4 identity matrix as nested lists.

    """
    return [list(row) for row in IDENTITY]


def multiply(a, b):
    """Multiply two 4x4 matrices (``a`` applied first, then ``b``).

    Args:
        a (list): Left matrix.
        b (list): Right matrix.

    Returns:
        list: The product ``a * b``.

    """
    return [
        [sum(a[r][k] * b[k][c] for k in range(4)) for c in range(4)]
        for r in range(4)
    ]


def compose(translate, rotate, scale):
    """Build a local matrix from Maya-style transform values.

    Rotation is in degrees with Maya's default ``xyz`` rotate order, so the
    result is ``S * Rx * Ry * Rz * T``. Pivots and shear are not modelled.

    Args:
        translate (tuple): Translation (x, y, z).
        rotate (tuple): Euler rotation in degrees (x, y, z).
        scale (tuple): Scale (x, y, z).

    Returns:
        list: The composed 4x4 matrix.

    """
    sx, sy, sz = scale
    matrix = [
        [sx, 0.0, 0.0, 0.0],
        [0.0, sy, 0.0, 0.0],
        [0.0, 0.0, sz, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
    for axis, degrees in enumerate(rotate):
        if degrees:
            matrix = multiply(matrix, _axis_rotation(axis, degrees))
    tx, ty, tz = translate
    move = identity()
    move[3][:3] = [tx, ty, tz]
    return multiply(matrix, move)


def transform_point(point, matrix):
    """Transform a 3D point by a 4x4 matrix.

    Args:
        point (tuple): Point (x, y, z).
        matrix (list): 4x4 matrix.

    Returns:
        tuple: The transformed point.

    """
    x, y, z = point
    return tuple(
        x * matrix[0][c] + y * matrix[1][c] + z * matrix[2][c] + matrix[3][c]
        for c in range(3)
    )


def is_identity(matrix, tolerance=1e-6):
    """Return True if ``matrix`` is the identity within ``tolerance``.

    Args:
        matrix (list): 4x4 matrix.
        tolerance (float): Allowed absolute difference per element.

    Returns:
        bool: Whether the matrix is (close to) identity.

    """
    return all(
        abs(matrix[r][c] - IDENTITY[r][c]) <= tolerance
        for r in range(4)
        for c in range(4)
    )


def _axis_rotation(axis, degrees):
    radians = math.radians(degrees)
    cos, sin = math.cos(radians), math.sin(radians)
    matrix = identity()
    i, j = [(1, 2), (2, 0), (0, 1)][axis]
    matrix[i][i] = cos
    matrix[i][j] = sin
    matrix[j][i] = -sin
    matrix[j][j] = cos
    return matrix
