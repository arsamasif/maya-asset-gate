"""Host-independent description of a Maya asset scene.

Checks and the USD publisher never talk to Maya directly. They read a
``SceneData`` object: a flat, ordered table of transform nodes keyed by
full DAG path, optional mesh arrays on each node, and the materials the
meshes use. The Maya adapter fills it from a live scene; tests and the
CLI load it from a JSON dump.

"""

import copy
import json
import os
from dataclasses import dataclass, field

from asset_gate import xform

SCHEMA_VERSION = 1
SEPARATOR = "|"
TEXTURE_SLOTS = ("base_color", "roughness", "metallic", "normal")


@dataclass
class UVSet:
    """UV coordinates plus a per face-vertex index into them."""

    uvs: list = field(default_factory=list)
    indices: list = field(default_factory=list)


@dataclass
class Mesh:
    """Polygon mesh arrays in object space, Maya-style."""

    points: list = field(default_factory=list)
    face_counts: list = field(default_factory=list)
    face_indices: list = field(default_factory=list)
    uv_sets: dict = field(default_factory=dict)
    material: str = None
    lamina_faces: list = field(default_factory=list)
    non_manifold_edges: list = field(default_factory=list)

    @property
    def face_count(self):
        """int: Number of polygons."""
        return len(self.face_counts)

    @property
    def triangle_count(self):
        """int: Number of triangles after a fan triangulation."""
        return sum(max(count - 2, 0) for count in self.face_counts)


@dataclass
class Material:
    """A surface material reduced to what UsdPreviewSurface can express."""

    name: str
    base_color: tuple = (0.18, 0.18, 0.18)
    roughness: float = 0.5
    metallic: float = 0.0
    textures: dict = field(default_factory=dict)


@dataclass
class Node:
    """A transform node, optionally carrying a mesh shape."""

    path: str
    translate: tuple = (0.0, 0.0, 0.0)
    rotate: tuple = (0.0, 0.0, 0.0)
    scale: tuple = (1.0, 1.0, 1.0)
    pivot: tuple = (0.0, 0.0, 0.0)
    history: list = field(default_factory=list)
    mesh: Mesh = None

    @property
    def name(self):
        """str: Short name, the last DAG path component."""
        return self.path.rsplit(SEPARATOR, 1)[-1]

    @property
    def parent_path(self):
        """str: Full path of the parent, or "" for a top-level node."""
        return self.path.rsplit(SEPARATOR, 1)[0]

    @property
    def depth(self):
        """int: Number of ancestors (0 for a top-level node)."""
        return self.path.count(SEPARATOR) - 1

    def local_matrix(self):
        """Return the node's local matrix from translate/rotate/scale.

        Returns:
            list: 4x4 matrix.

        """
        return xform.compose(self.translate, self.rotate, self.scale)


class SceneData:
    """An ordered collection of nodes and materials making up one asset.

    Args:
        name (str): Asset name; also the expected root node name.
        version (int): Asset version written to USD assetInfo.
        source_dir (str): Directory relative texture paths resolve against.

    """

    def __init__(self, name, version=1, source_dir=""):
        self.name = name
        self.version = version
        self.source_dir = source_dir
        self.nodes = {}
        self.materials = {}

    # -- building ----------------------------------------------------------

    def add_node(self, node):
        """Add a node; its parent must already exist.

        Args:
            node (Node): Node to add.

        Returns:
            Node: The added node.

        Raises:
            ValueError: If the path is malformed, taken or orphaned.

        """
        if not node.path.startswith(SEPARATOR) or node.path.endswith(SEPARATOR):
            raise ValueError("Node path must be a full DAG path: {0}".format(node.path))
        if node.path in self.nodes:
            raise ValueError("Duplicate node path: {0}".format(node.path))
        if node.parent_path and node.parent_path not in self.nodes:
            raise ValueError("Parent missing for node: {0}".format(node.path))
        self.nodes[node.path] = node
        return node

    def add_material(self, material):
        """Add or replace a material by name.

        Args:
            material (Material): Material to add.

        Returns:
            Material: The added material.

        """
        self.materials[material.name] = material
        return material

    # -- queries -----------------------------------------------------------

    def get(self, path):
        """Return the node at ``path``.

        Args:
            path (str): Full DAG path.

        Returns:
            Node: The node.

        Raises:
            KeyError: If no node has that path.

        """
        try:
            return self.nodes[path]
        except KeyError:
            raise KeyError("No node at path: {0}".format(path)) from None

    def roots(self):
        """Return top-level nodes in scene order.

        Returns:
            list: Nodes without a parent.

        """
        return [node for node in self.nodes.values() if not node.parent_path]

    def root(self):
        """Return the single asset root node.

        Returns:
            Node: The top-level node.

        Raises:
            ValueError: If there is not exactly one top-level node.

        """
        roots = self.roots()
        if len(roots) != 1:
            raise ValueError("Expected one root node, found {0}".format(len(roots)))
        return roots[0]

    def children(self, path):
        """Return direct children of ``path`` in scene order.

        Args:
            path (str): Parent path.

        Returns:
            list: Child nodes.

        """
        return [node for node in self.nodes.values() if node.parent_path == path]

    def descendants(self, path, include_self=False):
        """Return all nodes below ``path`` in scene order.

        Args:
            path (str): Ancestor path.
            include_self (bool): Also return the node at ``path``.

        Returns:
            list: Descendant nodes.

        """
        prefix = path + SEPARATOR
        found = [node for node in self.nodes.values() if node.path.startswith(prefix)]
        if include_self:
            found.insert(0, self.get(path))
        return found

    def mesh_nodes(self):
        """Return every node that carries a mesh.

        Returns:
            list: Mesh nodes in scene order.

        """
        return [node for node in self.nodes.values() if node.mesh is not None]

    def world_matrix(self, path):
        """Compose local matrices from the root down to ``path``.

        Args:
            path (str): Node path.

        Returns:
            list: 4x4 world matrix.

        """
        node = self.get(path)
        matrix = node.local_matrix()
        if node.parent_path:
            matrix = xform.multiply(matrix, self.world_matrix(node.parent_path))
        return matrix

    def world_bounds(self, path):
        """Return the world-space bounding box of meshes at or below ``path``.

        Args:
            path (str): Node path.

        Returns:
            tuple: ``(min, max)`` points, or None when there is no geometry.

        """
        points = []
        for node in self.descendants(path, include_self=True):
            if node.mesh is None:
                continue
            matrix = self.world_matrix(node.path)
            points.extend(xform.transform_point(p, matrix) for p in node.mesh.points)
        if not points:
            return None
        lower = tuple(min(p[axis] for p in points) for axis in range(3))
        upper = tuple(max(p[axis] for p in points) for axis in range(3))
        return lower, upper

    # -- edits -------------------------------------------------------------

    def rename(self, path, new_name):
        """Rename a node, updating the paths of all its descendants.

        Args:
            path (str): Current full path.
            new_name (str): New short name.

        Returns:
            str: The node's new full path.

        Raises:
            ValueError: If the name is invalid or the new path is taken.

        """
        if not new_name or SEPARATOR in new_name:
            raise ValueError("Invalid node name: {0!r}".format(new_name))
        node = self.get(path)
        new_path = node.parent_path + SEPARATOR + new_name
        if new_path in self.nodes:
            raise ValueError("Node already exists: {0}".format(new_path))
        renamed = {}
        for old, item in self.nodes.items():
            if old == path or old.startswith(path + SEPARATOR):
                item.path = new_path + old[len(path):]
            renamed[item.path] = item
        self.nodes = renamed
        return new_path

    def remove(self, path):
        """Remove a node and its descendants.

        Args:
            path (str): Node path.

        """
        self.get(path)
        for node in self.descendants(path, include_self=True):
            del self.nodes[node.path]

    def copy(self):
        """Return a deep copy, so fixes can run without touching the original.

        Returns:
            SceneData: Independent copy.

        """
        return copy.deepcopy(self)

    # -- serialization -----------------------------------------------------

    def to_dict(self):
        """Serialize to plain JSON-compatible data.

        Returns:
            dict: Scene description.

        """
        return {
            "schema": SCHEMA_VERSION,
            "name": self.name,
            "version": self.version,
            "nodes": [_node_to_dict(node) for node in self.nodes.values()],
            "materials": [_material_to_dict(m) for m in self.materials.values()],
        }

    @classmethod
    def from_dict(cls, data, source_dir=""):
        """Build a scene from the output of ``to_dict``.

        Args:
            data (dict): Scene description.
            source_dir (str): Directory relative texture paths resolve against.

        Returns:
            SceneData: The scene.

        Raises:
            ValueError: If the schema version is unsupported.

        """
        schema = data.get("schema", SCHEMA_VERSION)
        if schema != SCHEMA_VERSION:
            raise ValueError("Unsupported scene schema: {0}".format(schema))
        scene = cls(data["name"], data.get("version", 1), source_dir)
        for item in data.get("materials", []):
            scene.add_material(_material_from_dict(item))
        for item in data.get("nodes", []):
            scene.add_node(_node_from_dict(item))
        return scene


def load(path):
    """Load a scene from a JSON file.

    Args:
        path (str): JSON file written by ``save`` or the Maya adapter.

    Returns:
        SceneData: The scene, with ``source_dir`` set to the file's folder.

    Raises:
        FileNotFoundError: If the file does not exist.

    """
    if not os.path.isfile(path):
        raise FileNotFoundError("Missing scene file: {0}".format(path))
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    return SceneData.from_dict(data, os.path.dirname(os.path.abspath(path)))


def save(scene, path):
    """Write a scene to a JSON file.

    Args:
        scene (SceneData): Scene to write.
        path (str): Destination file.

    """
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(scene.to_dict(), handle, indent=1)
        handle.write("\n")


def _node_to_dict(node):
    data = {
        "path": node.path,
        "translate": list(node.translate),
        "rotate": list(node.rotate),
        "scale": list(node.scale),
        "pivot": list(node.pivot),
        "history": list(node.history),
    }
    if node.mesh is not None:
        mesh = node.mesh
        data["mesh"] = {
            "points": [list(p) for p in mesh.points],
            "face_counts": list(mesh.face_counts),
            "face_indices": list(mesh.face_indices),
            "uv_sets": {
                name: {"uvs": [list(uv) for uv in uv_set.uvs], "indices": list(uv_set.indices)}
                for name, uv_set in mesh.uv_sets.items()
            },
            "material": mesh.material,
            "lamina_faces": list(mesh.lamina_faces),
            "non_manifold_edges": list(mesh.non_manifold_edges),
        }
    return data


def _node_from_dict(data):
    mesh = None
    if data.get("mesh") is not None:
        raw = data["mesh"]
        mesh = Mesh(
            points=[tuple(p) for p in raw.get("points", [])],
            face_counts=list(raw.get("face_counts", [])),
            face_indices=list(raw.get("face_indices", [])),
            uv_sets={
                name: UVSet([tuple(uv) for uv in item["uvs"]], list(item["indices"]))
                for name, item in raw.get("uv_sets", {}).items()
            },
            material=raw.get("material"),
            lamina_faces=list(raw.get("lamina_faces", [])),
            non_manifold_edges=list(raw.get("non_manifold_edges", [])),
        )
    return Node(
        path=data["path"],
        translate=tuple(data.get("translate", (0.0, 0.0, 0.0))),
        rotate=tuple(data.get("rotate", (0.0, 0.0, 0.0))),
        scale=tuple(data.get("scale", (1.0, 1.0, 1.0))),
        pivot=tuple(data.get("pivot", (0.0, 0.0, 0.0))),
        history=list(data.get("history", [])),
        mesh=mesh,
    )


def _material_to_dict(material):
    return {
        "name": material.name,
        "base_color": list(material.base_color),
        "roughness": material.roughness,
        "metallic": material.metallic,
        "textures": dict(material.textures),
    }


def _material_from_dict(data):
    unknown = set(data.get("textures", {})) - set(TEXTURE_SLOTS)
    if unknown:
        raise ValueError("Unknown texture slots: {0}".format(sorted(unknown)))
    return Material(
        name=data["name"],
        base_color=tuple(data.get("base_color", (0.18, 0.18, 0.18))),
        roughness=float(data.get("roughness", 0.5)),
        metallic=float(data.get("metallic", 0.0)),
        textures=dict(data.get("textures", {})),
    )
