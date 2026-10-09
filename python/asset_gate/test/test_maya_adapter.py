"""Maya integration tests; run with ``mayapy -m pytest``.

They build a tiny asset with maya.cmds, read it back through the adapter,
fix it in Maya and publish it. Skipped when Maya is not importable.

"""

import pytest

pytest.importorskip("maya.standalone")

import maya.standalone  # noqa: E402

maya.standalone.initialize(name="python")

from maya import cmds  # noqa: E402

from asset_gate import gate  # noqa: E402
from asset_gate import maya_adapter  # noqa: E402
from asset_gate import report  # noqa: E402
from asset_gate import usd_publish  # noqa: E402


@pytest.fixture
def chair():
    cmds.file(new=True, force=True)
    root = cmds.group(empty=True, name="chair")
    geo = cmds.group(empty=True, name="geo", parent=root)
    lod0 = cmds.group(empty=True, name="LOD0", parent=geo)
    seat = cmds.polyCube(name="seat_LOD0_GEO", width=40, height=5, depth=40)[0]
    cmds.parent(seat, lod0)
    cmds.move(0, 45, 0, "|chair|geo|LOD0|seat_LOD0_GEO")
    shader = cmds.shadingNode("standardSurface", asShader=True, name="wood_MTL")
    engine = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name="wood_SG")
    cmds.connectAttr(shader + ".outColor", engine + ".surfaceShader")
    cmds.sets("|chair|geo|LOD0|seat_LOD0_GEO", edit=True, forceElement=engine)
    return root


def test_build_scene_reads_meshes_and_materials(chair):
    scene = maya_adapter.build_scene("chair")
    seat = scene.get("|chair|geo|LOD0|seat_LOD0_GEO")
    assert seat.mesh.face_count == 6
    assert "map1" in seat.mesh.uv_sets
    assert seat.mesh.material == "wood_MTL"
    assert "polyCube" in seat.history
    assert seat.translate == pytest.approx((0, 45, 0))


def test_fix_in_maya_then_publish(chair, tmp_path):
    context = maya_adapter.make_context("chair")
    results = gate.validate(context, fix=True)
    assert report.summarize(results)["publishable"], report.format_console(results)
    assert not cmds.listHistory("|chair|geo|LOD0|seat_LOD0_GEO", pruneDagObjects=True)
    assert cmds.getAttr("|chair|geo|LOD0|seat_LOD0_GEO.translateY") == pytest.approx(0)
    written = usd_publish.publish(context.scene, str(tmp_path))
    assert written.asset.endswith("chair.usda")


def test_drop_installer_writes_the_module_file(tmp_path, monkeypatch):
    import importlib.util
    import os

    from asset_gate import install

    repo = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    modules = str(tmp_path / "modules")
    monkeypatch.setattr(install, "user_modules_dir", lambda: modules)
    spec = importlib.util.spec_from_file_location(
        "install_asset_gate", os.path.join(repo, "install_asset_gate.py")
    )
    dropped = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dropped)

    dropped.onMayaDroppedPythonFile()

    with open(os.path.join(modules, "asset_gate.mod"), encoding="utf-8") as handle:
        assert handle.read() == install.module_text(repo)
    assert install.add_shelf_button() is None
