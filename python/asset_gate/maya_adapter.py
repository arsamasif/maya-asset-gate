"""Maya side of asset_gate: build SceneData from Maya and apply fixes there.

Mesh arrays are read with ``maya.api.OpenMaya`` (MFnMesh), everything else
with ``maya.cmds``. ``MayaEditor`` implements the same fix interface as
``editor.SceneEditor`` by running the matching Maya commands, and rebuilds
the SceneData after each fix so checks re-run against the real scene.

Only this module (and ``ui``) imports Maya.

"""

import os
import re

import maya.api.OpenMaya as om
from maya import cmds

from asset_gate import check
from asset_gate import gate
from asset_gate import scene as scene_mod

COMPONENT_RE = re.compile(r"\[(\d+)(?::(\d+))?\]")
UDIM_RE = re.compile(r"1\d{3}(?=\D*$)")
UDIM_TILING_MODE = 3
SHADER_ATTRS = {
    # node type: (base color, roughness, metallic, normal input)
    "standardSurface": ("baseColor", "specularRoughness", "metalness", "normalCamera"),
    "aiStandardSurface": ("baseColor", "specularRoughness", "metalness", "normalCamera"),
    "usdPreviewSurface": ("diffuseColor", "roughness", "metallic", "normal"),
    "lambert": ("color", None, None, "normalCamera"),
    "blinn": ("color", None, None, "normalCamera"),
    "phong": ("color", None, None, "normalCamera"),
}
MAYA_USD_PLUGIN = "mayaUsdPlugin"


# -- reading --------------------------------------------------------------


def find_root(root=None):
    """Resolve the asset root transform.

    Args:
        root (str): Node name or path. If None, the top-level ancestor of the
            first selected transform, or the only non-camera assembly.

    Returns:
        str: Full DAG path of the root.

    Raises:
        ValueError: If no single root can be determined.

    """
    if root:
        found = cmds.ls(root, long=True, type="transform")
        if len(found) != 1:
            raise ValueError("Root transform not found or ambiguous: {0}".format(root))
        return found[0]
    selection = cmds.ls(selection=True, long=True, type="transform")
    if selection:
        return "|" + selection[0].split("|")[1]
    assemblies = [
        node for node in cmds.ls(assemblies=True, long=True)
        if not cmds.listRelatives(node, shapes=True, type="camera")
    ]
    if len(assemblies) != 1:
        raise ValueError("Select the asset root; found {0} top-level nodes".format(len(assemblies)))
    return assemblies[0]


def build_scene(root=None, name=None, version=1):
    """Read the asset under ``root`` into a SceneData.

    The asset root becomes the SceneData root, so paths start at the root
    even if it is parented under something else in Maya.

    Args:
        root (str): Root transform; see ``find_root``.
        name (str): Asset name, defaults to the root's short name.
        version (int): Asset version.

    Returns:
        SceneData: The scene description.

    """
    root_path = find_root(root)
    prefix = root_path.rsplit("|", 1)[0]
    scene_file = cmds.file(query=True, sceneName=True)
    scene = scene_mod.SceneData(
        name or root_path.rsplit("|", 1)[-1].split(":")[-1],
        version,
        os.path.dirname(scene_file) if scene_file else "",
    )
    for path in _walk(root_path):
        node = _read_node(path)
        node.path = path[len(prefix):]
        scene.add_node(node)
        if node.mesh is not None and node.mesh.material:
            if node.mesh.material not in scene.materials:
                scene.add_material(_read_material(node.mesh.material))
    return scene


def dump_scene(path, root=None, name=None, version=1):
    """Write the asset under ``root`` to a SceneData JSON file.

    Args:
        path (str): Destination JSON file.
        root (str): Root transform; see ``find_root``.
        name (str): Asset name.
        version (int): Asset version.

    Returns:
        SceneData: The scene that was written.

    """
    scene = build_scene(root, name, version)
    scene_mod.save(scene, path)
    return scene


def _walk(path):
    yield path
    for child in cmds.listRelatives(path, children=True, fullPath=True, type="transform") or []:
        if cmds.nodeType(child) == "transform":
            yield from _walk(child)


def _read_node(path):
    node = scene_mod.Node(
        path=path,
        translate=tuple(cmds.getAttr(path + ".translate")[0]),
        rotate=tuple(cmds.getAttr(path + ".rotate")[0]),
        scale=tuple(cmds.getAttr(path + ".scale")[0]),
        pivot=tuple(cmds.xform(path, query=True, worldSpace=True, rotatePivot=True)),
    )
    shapes = cmds.listRelatives(
        path, shapes=True, fullPath=True, type="mesh", noIntermediate=True) or []
    if shapes:
        node.mesh = _read_mesh(shapes[0])
        node.history = [
            cmds.nodeType(item)
            for item in cmds.listHistory(shapes[0], pruneDagObjects=True) or []
        ]
    return node


def _read_mesh(shape):
    selection = om.MSelectionList()
    selection.add(shape)
    fn_mesh = om.MFnMesh(selection.getDagPath(0))
    counts, indices = fn_mesh.getVertices()
    mesh = scene_mod.Mesh(
        points=[(p.x, p.y, p.z) for p in fn_mesh.getPoints(om.MSpace.kObject)],
        face_counts=list(counts),
        face_indices=list(indices),
    )
    for set_name in fn_mesh.getUVSetNames():
        us, vs = fn_mesh.getUVs(set_name)
        _, uv_ids = fn_mesh.getAssignedUVs(set_name)
        mesh.uv_sets[set_name] = scene_mod.UVSet(list(zip(us, vs)), list(uv_ids))
    mesh.lamina_faces = _component_indices(cmds.polyInfo(shape, laminaFaces=True))
    mesh.non_manifold_edges = _component_indices(cmds.polyInfo(shape, nonManifoldEdges=True))
    mesh.material = _assigned_shader(shape)
    return mesh


def _component_indices(components):
    indices = []
    for component in components or []:
        for match in COMPONENT_RE.finditer(component):
            start = int(match.group(1))
            end = int(match.group(2) or start)
            indices.extend(range(start, end + 1))
    return sorted(set(indices))


def _assigned_shader(shape):
    engines = cmds.listConnections(shape, type="shadingEngine") or []
    for engine in dict.fromkeys(engines):
        shaders = cmds.listConnections(
            engine + ".surfaceShader", source=True, destination=False) or []
        if shaders:
            return shaders[0]
    return None


def _read_material(shader):
    attrs = SHADER_ATTRS.get(cmds.nodeType(shader), ("color", None, None, None))
    color_attr, roughness_attr, metallic_attr, normal_attr = attrs
    material = scene_mod.Material(name=shader)
    if cmds.attributeQuery(color_attr, node=shader, exists=True):
        material.base_color = tuple(cmds.getAttr(shader + "." + color_attr)[0])
        _add_texture(material, "base_color", shader + "." + color_attr)
    if roughness_attr:
        material.roughness = float(cmds.getAttr(shader + "." + roughness_attr))
        _add_texture(material, "roughness", shader + "." + roughness_attr)
    if metallic_attr:
        material.metallic = float(cmds.getAttr(shader + "." + metallic_attr))
        _add_texture(material, "metallic", shader + "." + metallic_attr)
    if normal_attr and cmds.attributeQuery(normal_attr, node=shader, exists=True):
        bumps = cmds.listConnections(
            shader + "." + normal_attr, source=True, destination=False, type="bump2d") or []
        plug = bumps[0] + ".bumpValue" if bumps else shader + "." + normal_attr
        _add_texture(material, "normal", plug)
    return material


def _add_texture(material, slot, plug):
    files = cmds.listConnections(plug, source=True, destination=False, type="file") or []
    if not files:
        return
    path = cmds.getAttr(files[0] + ".fileTextureName")
    if cmds.getAttr(files[0] + ".uvTilingMode") == UDIM_TILING_MODE:
        path = UDIM_RE.sub("<UDIM>", path)
    material.textures[slot] = path


# -- fixing ---------------------------------------------------------------


class MayaEditor:
    """Apply fix operations with Maya commands.

    SceneData paths start at the asset root; ``prefix`` maps them back to
    Maya DAG paths when the root has a parent.

    Args:
        root (str): Root transform path.
        name (str): Asset name.
        version (int): Asset version.

    """

    def __init__(self, root, name=None, version=1):
        self.root = find_root(root)
        self.prefix = self.root.rsplit("|", 1)[0]
        self.name = name
        self.version = version

    def freeze_transforms(self, path):
        """Run ``makeIdentity -apply`` on a node and its children."""
        cmds.makeIdentity(self._dag(path), apply=True, translate=True, rotate=True,
                          scale=True, normal=0, preserveNormals=True)

    def delete_history(self, path):
        """Delete construction history on a node."""
        cmds.delete(self._dag(path), constructionHistory=True)

    def rename(self, path, new_name):
        """Rename a node and return its new SceneData path."""
        dag = self._dag(path)
        result = cmds.rename(dag, new_name)
        new_dag = dag.rsplit("|", 1)[0] + "|" + result.rsplit("|", 1)[-1]
        if dag == self.root:
            self.root = new_dag
        return new_dag[len(self.prefix):]

    def set_pivot(self, path, point):
        """Move the rotate and scale pivots to a world-space point."""
        cmds.xform(self._dag(path), worldSpace=True, pivots=tuple(point))

    def delete(self, path):
        """Delete a node and its children."""
        cmds.delete(self._dag(path))

    def refresh(self):
        """Re-read the scene after edits."""
        return build_scene(self.root, self.name, self.version)

    def _dag(self, path):
        return self.prefix + path


def make_context(root=None, config=None, name=None, version=1):
    """Build a check context for the asset in the open Maya scene.

    Args:
        root (str): Root transform; see ``find_root``.
        config (dict): Loaded config, or None for defaults.
        name (str): Asset name.
        version (int): Asset version.

    Returns:
        Context: Context with a ``MayaEditor``.

    """
    editor = MayaEditor(root, name, version)
    return check.Context(scene=editor.refresh(), config=config or {}, editor=editor)


def validate(root=None, config=None, fix=False):
    """Validate the asset in the open scene; convenient for shelf buttons.

    Args:
        root (str): Root transform; see ``find_root``.
        config (dict): Loaded config, or None for defaults.
        fix (bool): Apply fixes in Maya.

    Returns:
        list: ``CheckResult`` objects.

    """
    return gate.validate(make_context(root, config), fix=fix)


def export_with_maya_usd(path, root=None):
    """Optionally export the asset's meshes with the mayaUsd plugin.

    The core publisher writes geometry itself; this is for studios that
    want Maya's exporter (normals, creases, extra primvars) for geo.usda.

    Args:
        path (str): Destination ``.usd``/``.usda`` file.
        root (str): Root transform; see ``find_root``.

    Returns:
        str: The written path.

    """
    if not cmds.pluginInfo(MAYA_USD_PLUGIN, query=True, loaded=True):
        cmds.loadPlugin(MAYA_USD_PLUGIN, quiet=True)
    cmds.select(find_root(root), replace=True)
    cmds.mayaUSDExport(
        file=path,
        selection=True,
        exportUVs=True,
        exportDisplayColor=True,
        defaultMeshScheme="none",
        shadingMode="none",
    )
    return path
