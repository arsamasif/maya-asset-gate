"""Scene builders shared by the tests and the example files.

``chair_scene`` returns a clean two-LOD asset that passes every check;
tests break it in one specific way to exercise a single check.

"""

from asset_gate import scene as scene_mod

BOX_FACES = (
    # origin corner, u direction, v direction (u x v is the outward normal)
    ((0.5, -0.5, 0.5), (0, 0, -1), (0, 1, 0)),
    ((-0.5, -0.5, -0.5), (0, 0, 1), (0, 1, 0)),
    ((-0.5, 0.5, 0.5), (1, 0, 0), (0, 0, -1)),
    ((-0.5, -0.5, -0.5), (1, 0, 0), (0, 0, 1)),
    ((-0.5, -0.5, 0.5), (1, 0, 0), (0, 1, 0)),
    ((0.5, -0.5, -0.5), (-1, 0, 0), (0, 1, 0)),
)


def box(size=(1.0, 1.0, 1.0), center=(0.0, 0.0, 0.0), divisions=1, material=None):
    """Build a box mesh whose faces are ``divisions`` x ``divisions`` quad grids.

    Args:
        size (tuple): Box size per axis.
        center (tuple): Box center.
        divisions (int): Quads per face edge.
        material (str): Material name to assign.

    Returns:
        Mesh: Box with a ``map1`` UV set laid out in a 3x2 atlas.

    """
    mesh = scene_mod.Mesh(material=material)
    uvs = []
    step = 1.0 / divisions
    for face_index, (origin, du, dv) in enumerate(BOX_FACES):
        base = len(mesh.points)
        tile_u, tile_v = (face_index % 3) / 3.0, (face_index // 3) / 2.0
        for j in range(divisions + 1):
            for i in range(divisions + 1):
                local = [origin[a] + du[a] * i * step + dv[a] * j * step for a in range(3)]
                mesh.points.append(tuple(center[a] + local[a] * size[a] for a in range(3)))
                uvs.append((tile_u + i * step / 3.0, tile_v + j * step / 2.0))
        row = divisions + 1
        for j in range(divisions):
            for i in range(divisions):
                corner = base + j * row + i
                mesh.face_counts.append(4)
                mesh.face_indices.extend([corner, corner + 1, corner + row + 1, corner + row])
    mesh.uv_sets["map1"] = scene_mod.UVSet(uvs, list(mesh.face_indices))
    return mesh


def chair_scene(lod0_divisions=4):
    """Return a clean chair asset with two LODs and one material.

    Args:
        lod0_divisions (int): Quads per box face edge in LOD0.

    Returns:
        SceneData: Scene that passes every built-in check.

    """
    scene = scene_mod.SceneData("chair", version=3)
    scene.add_material(scene_mod.Material("wood_MTL", base_color=(0.45, 0.3, 0.18),
                                          roughness=0.6))
    for path in ("|chair", "|chair|geo", "|chair|geo|LOD0", "|chair|geo|LOD1"):
        scene.add_node(scene_mod.Node(path))
    parts = {
        "seat": ((40.0, 5.0, 40.0), (0.0, 45.0, 0.0)),
        "back": ((40.0, 50.0, 5.0), (0.0, 72.5, -17.5)),
        "legs": ((40.0, 42.5, 40.0), (0.0, 21.25, 0.0)),
    }
    for lod, divisions in (("LOD0", lod0_divisions), ("LOD1", 1)):
        for part, (size, center) in parts.items():
            scene.add_node(scene_mod.Node(
                "|chair|geo|{0}|{1}_{0}_GEO".format(lod, part),
                mesh=box(size, center, divisions, "wood_MTL"),
            ))
    return scene
