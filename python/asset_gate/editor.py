"""Scene edits used by check fixes, applied to a SceneData object.

Fixes never touch a host directly. They call a small editor interface
(freeze, delete history, rename, set pivot, delete) and the runner calls
``refresh`` afterwards to get the updated scene. ``SceneEditor`` is the
pure-Python implementation used by the CLI and tests; the Maya adapter
provides one with the same methods that runs the matching Maya commands.

"""

from asset_gate import xform


class SceneEditor:
    """Apply fix operations to a ``SceneData`` in place.

    Args:
        scene (SceneData): Scene to edit.

    """

    def __init__(self, scene):
        self.scene = scene
        self.log = []

    def freeze_transforms(self, path):
        """Bake the transforms of ``path`` and its descendants into points.

        Mirrors Maya's ``makeIdentity -apply``: every transform in the
        subtree becomes identity and mesh points keep their world position.

        Args:
            path (str): Node to freeze.

        """
        scene = self.scene
        node = scene.get(path)
        for item in scene.descendants(path, include_self=True):
            if item.mesh is None:
                continue
            matrix = self._matrix_between(item.path, node.parent_path)
            item.mesh.points = [xform.transform_point(p, matrix) for p in item.mesh.points]
        for item in scene.descendants(path, include_self=True):
            item.translate = (0.0, 0.0, 0.0)
            item.rotate = (0.0, 0.0, 0.0)
            item.scale = (1.0, 1.0, 1.0)
        self.log.append(("freeze_transforms", path))

    def delete_history(self, path):
        """Remove construction history from a node.

        Args:
            path (str): Node path.

        """
        self.scene.get(path).history = []
        self.log.append(("delete_history", path))

    def rename(self, path, new_name):
        """Rename a node.

        Args:
            path (str): Node path.
            new_name (str): New short name.

        Returns:
            str: The new full path.

        """
        new_path = self.scene.rename(path, new_name)
        self.log.append(("rename", path, new_name))
        return new_path

    def set_pivot(self, path, point):
        """Move a node's world-space pivot without moving geometry.

        Args:
            path (str): Node path.
            point (tuple): World-space pivot position.

        """
        self.scene.get(path).pivot = tuple(float(v) for v in point)
        self.log.append(("set_pivot", path, tuple(point)))

    def delete(self, path):
        """Delete a node and its children.

        Args:
            path (str): Node path.

        """
        self.scene.remove(path)
        self.log.append(("delete", path))

    def refresh(self):
        """Return the current scene after edits.

        Returns:
            SceneData: The edited scene.

        """
        return self.scene

    def _matrix_between(self, path, stop_path):
        matrix = xform.identity()
        current = path
        while current and current != stop_path:
            node = self.scene.get(current)
            matrix = xform.multiply(matrix, node.local_matrix())
            current = node.parent_path
        return matrix
