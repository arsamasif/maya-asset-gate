"""Tests for the pure SceneData editor used by fixes.

"""

import pytest

from asset_gate import editor
from asset_gate.test import scenes


def test_freeze_keeps_world_positions_and_resets_subtree():
    scene = scenes.chair_scene()
    scene.get("|chair|geo").translate = (0.0, 5.0, 0.0)
    scene.get("|chair|geo").rotate = (0.0, 90.0, 0.0)
    seat = "|chair|geo|LOD0|seat_LOD0_GEO"
    scene.get(seat).scale = (2.0, 1.0, 1.0)
    before = scene.world_bounds(seat)

    scene_editor = editor.SceneEditor(scene)
    scene_editor.freeze_transforms("|chair|geo")

    after = scene.world_bounds(seat)
    assert after[0] == pytest.approx(before[0])
    assert after[1] == pytest.approx(before[1])
    for node in scene.descendants("|chair|geo", include_self=True):
        assert node.translate == (0.0, 0.0, 0.0)
        assert node.scale == (1.0, 1.0, 1.0)
    assert scene_editor.log == [("freeze_transforms", "|chair|geo")]


def test_simple_edits():
    scene = scenes.chair_scene()
    scene_editor = editor.SceneEditor(scene)
    scene.get("|chair").history = ["polyCube"]
    scene_editor.delete_history("|chair")
    scene_editor.set_pivot("|chair", (1, 2, 3))
    new_path = scene_editor.rename("|chair|geo|LOD1", "LOD9")
    scene_editor.delete(new_path)
    assert scene.get("|chair").history == []
    assert scene.get("|chair").pivot == (1.0, 2.0, 3.0)
    assert "|chair|geo|LOD9" not in scene.nodes
    assert scene_editor.refresh() is scene
