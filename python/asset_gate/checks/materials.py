"""Material checks: every mesh is shaded, and every texture exists on disk.

Relative texture paths resolve against the scene's ``source_dir``. Paths
with a ``<UDIM>`` token pass when at least one tile file is found.

"""

import glob
import os

from asset_gate import check

UDIM_TOKEN = "<UDIM>"


class MaterialAssigned(check.BaseCheck):
    """Every mesh must reference a material defined in the scene."""

    id = "material.assigned"
    label = "Materials assigned"
    category = "material"
    severity = check.WARNING
    order = 10
    description = "Meshes have a known material (otherwise USD gets no binding)."

    def run(self, context):
        scene = context.scene
        issues = []
        for node in scene.mesh_nodes():
            name = node.mesh.material
            if not name:
                issues.append(check.Issue("no material assigned", node.path))
            elif name not in scene.materials:
                issues.append(check.Issue(
                    "unknown material {0!r}".format(name), node.path, {"material": name}))
        return issues


class TexturesExist(check.BaseCheck):
    """Texture files referenced by materials must exist."""

    id = "material.textures"
    label = "Textures exist"
    category = "material"
    order = 20
    description = "Every texture path resolves to a file (UDIM-aware)."

    def run(self, context):
        scene = context.scene
        issues = []
        for material in scene.materials.values():
            for slot, path in sorted(material.textures.items()):
                if not texture_exists(path, scene.source_dir):
                    issues.append(check.Issue(
                        "{0}.{1}: missing texture {2}".format(material.name, slot, path),
                        "", {"material": material.name, "slot": slot, "path": path}))
        return issues


def resolve_texture(path, source_dir):
    """Return an absolute texture path.

    Args:
        path (str): Texture path as stored on the material.
        source_dir (str): Folder relative paths are relative to.

    Returns:
        str: Absolute path (tokens are kept).

    """
    if os.path.isabs(path) or not source_dir:
        return path
    return os.path.normpath(os.path.join(source_dir, path))


def texture_exists(path, source_dir=""):
    """Return True if the texture (or any UDIM tile of it) is on disk.

    Args:
        path (str): Texture path, possibly with a ``<UDIM>`` token.
        source_dir (str): Folder relative paths are relative to.

    Returns:
        bool: Whether a file was found.

    """
    if not path:
        return False
    resolved = resolve_texture(path, source_dir)
    if UDIM_TOKEN in resolved:
        pattern = glob.escape(resolved).replace(glob.escape(UDIM_TOKEN), "[1-9][0-9][0-9][0-9]")
        return bool(glob.glob(pattern))
    return os.path.isfile(resolved)
