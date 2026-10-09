"""Tests for the SceneData model, its JSON round trip and xform math.

"""

import math

import pytest

from asset_gate import scene as scene_mod
from asset_gate import xform
from asset_gate.test import scenes


def test_json_round_trip(tmp_path):
    original = scenes.chair_scene()
    original.get("|chair|geo").history = ["polyCube"]
    path = str(tmp_path / "chair.json")
    scene_mod.save(original, path)
    loaded = scene_mod.load(path)
    assert loaded.to_dict() == original.to_dict()
    assert loaded.source_dir == str(tmp_path)


def test_load_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        scene_mod.load(str(tmp_path / "nope.json"))


def test_unsupported_schema_raises():
    with pytest.raises(ValueError):
        scene_mod.SceneData.from_dict({"schema": 99, "name": "x"})


def test_unknown_texture_slot_raises():
    data = {"name": "x", "materials": [{"name": "m", "textures": {"gloss": "a.png"}}]}
    with pytest.raises(ValueError):
        scene_mod.SceneData.from_dict(data)


def test_add_node_requires_parent_and_unique_path():
    scene = scene_mod.SceneData("a")
    scene.add_node(scene_mod.Node("|a"))
    with pytest.raises(ValueError):
        scene.add_node(scene_mod.Node("|a"))
    with pytest.raises(ValueError):
        scene.add_node(scene_mod.Node("|missing|child"))
    with pytest.raises(ValueError):
        scene.add_node(scene_mod.Node("relative"))


def test_rename_updates_descendants_and_keeps_order():
    scene = scenes.chair_scene()
    order = list(scene.nodes)
    new_path = scene.rename("|chair|geo", "mesh_GRP")
    assert new_path == "|chair|mesh_GRP"
    assert "|chair|mesh_GRP|LOD0|seat_LOD0_GEO" in scene.nodes
    assert all(node.path == path for path, node in scene.nodes.items())
    assert len(scene.nodes) == len(order)
    with pytest.raises(ValueError):
        scene.rename("|chair|mesh_GRP", "a|b")


def test_remove_drops_subtree():
    scene = scenes.chair_scene()
    scene.remove("|chair|geo|LOD1")
    assert not [path for path in scene.nodes if "LOD1" in path]


def test_world_bounds_follow_parent_transforms():
    scene = scenes.chair_scene()
    lower, upper = scene.world_bounds("|chair")
    assert lower == pytest.approx((-20.0, 0.0, -20.0))
    scene.get("|chair").translate = (0.0, 10.0, 0.0)
    lower, _ = scene.world_bounds("|chair|geo|LOD0")
    assert lower[1] == pytest.approx(10.0)


def test_mesh_counts():
    mesh = scenes.box(divisions=2)
    assert mesh.face_count == 24
    assert mesh.triangle_count == 48


def test_rotation_matches_maya_convention():
    matrix = xform.compose((0, 0, 0), (0, 90, 0), (1, 1, 1))
    assert xform.transform_point((1, 0, 0), matrix) == pytest.approx((0, 0, -1))
    matrix = xform.compose((5, 0, 0), (0, 0, 90), (2, 2, 2))
    assert xform.transform_point((1, 0, 0), matrix) == pytest.approx((5, 2, 0))


def test_compose_rotation_order_is_xyz():
    combined = xform.compose((0, 0, 0), (30, 45, 60), (1, 1, 1))
    expected = xform.identity()
    for axis, degrees in enumerate((30, 45, 60)):
        rotate = [0, 0, 0]
        rotate[axis] = degrees
        expected = xform.multiply(expected, xform.compose((0, 0, 0), rotate, (1, 1, 1)))
    assert all(math.isclose(a, b, abs_tol=1e-9)
               for ra, rb in zip(combined, expected) for a, b in zip(ra, rb))
    assert xform.is_identity(xform.compose((0, 0, 0), (0, 0, 0), (1, 1, 1)))
