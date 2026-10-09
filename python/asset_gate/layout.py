"""Asset hierarchy conventions shared by checks and the publisher.

An asset is expected to look like::

    |chair                  root, named after the asset
        |geo
            |LOD0           one group per level of detail
                |seat_LOD0_GEO
            |LOD1
                |seat_LOD1_GEO
            |proxy          optional low-cost stand-in

Meshes that sit under ``geo`` but outside any ``LODn`` group count as LOD0,
so a simple single-LOD asset needs no LOD groups at all.

"""

import re

from asset_gate import scene as scene_mod

GEO_GROUP = "geo"
PROXY_GROUP = "proxy"
DEFAULT_LOD = "LOD0"
LOD_GROUP_RE = re.compile(r"^LOD(\d+)$")
LOD_TOKEN_RE = re.compile(r"_LOD(\d+)(?=_|$)")


def lod_of(path):
    """Return the LOD group name a node lives under.

    Args:
        path (str): Full DAG path.

    Returns:
        str: ``"LODn"``, ``"proxy"`` for proxy geometry, or the default LOD.

    """
    for part in path.split(scene_mod.SEPARATOR):
        if part == PROXY_GROUP:
            return PROXY_GROUP
        if LOD_GROUP_RE.match(part):
            return part
    return DEFAULT_LOD


def lod_index(lod):
    """Return the numeric index of an ``LODn`` name.

    Args:
        lod (str): LOD name.

    Returns:
        int: The index.

    Raises:
        ValueError: If ``lod`` is not an LOD name.

    """
    match = LOD_GROUP_RE.match(lod)
    if not match:
        raise ValueError("Not an LOD name: {0}".format(lod))
    return int(match.group(1))


def meshes_by_lod(scene):
    """Group the render meshes of a scene by LOD, ignoring proxy geometry.

    Args:
        scene (SceneData): Scene to inspect.

    Returns:
        dict: ``{"LOD0": [Node, ...], ...}`` sorted by LOD index.

    """
    grouped = {}
    for node in scene.mesh_nodes():
        lod = lod_of(node.path)
        if lod != PROXY_GROUP:
            grouped.setdefault(lod, []).append(node)
    return dict(sorted(grouped.items(), key=lambda item: lod_index(item[0])))


def proxy_meshes(scene):
    """Return the meshes placed under a ``proxy`` group.

    Args:
        scene (SceneData): Scene to inspect.

    Returns:
        list: Proxy mesh nodes.

    """
    return [node for node in scene.mesh_nodes() if lod_of(node.path) == PROXY_GROUP]


def base_name(name):
    """Strip the ``_LODn`` token from a mesh name.

    Args:
        name (str): Short node name such as ``seat_LOD1_GEO``.

    Returns:
        str: The LOD-independent name, e.g. ``seat_GEO``.

    """
    return LOD_TOKEN_RE.sub("", name)
