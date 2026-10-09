"""Tests for every built-in check: clean scene passes, broken scene fails.

Each test breaks the clean chair in one way, checks the issue that comes
back and, for fixable checks, that the fix clears it.

"""

import pytest

from asset_gate import gate
from asset_gate import runner
from asset_gate import scene as scene_mod
from asset_gate.checks import hierarchy
from asset_gate.checks import lod
from asset_gate.checks import materials
from asset_gate.checks import naming
from asset_gate.checks import topology
from asset_gate.checks import transforms
from asset_gate.checks import uvs
from asset_gate.test import scenes

SEAT = "|chair|geo|LOD0|seat_LOD0_GEO"


@pytest.fixture
def chair():
    return scenes.chair_scene()


def _issues(check, scene, config=None):
    return check.run(gate.make_context(scene, config))


def _fix(check, scene, config=None):
    context = gate.make_context(scene, config)
    result = runner.fix_check(check, context, runner.run_check(check, context))
    return result


@pytest.mark.parametrize("check_cls", [
    hierarchy.SingleRoot, hierarchy.EmptyGroups, naming.NamingConvention,
    naming.UniqueNames, transforms.FrozenTransforms, transforms.NoHistory,
    transforms.PivotPlacement, topology.NoNgons, topology.CleanManifold,
    uvs.UVSetsPresent, uvs.UVRange, materials.MaterialAssigned,
    materials.TexturesExist, lod.PolyBudget, lod.LODConsistency,
])
def test_clean_scene_passes(chair, check_cls):
    assert _issues(check_cls(), chair) == []


def test_single_root(chair):
    chair.add_node(scene_mod.Node("|stray"))
    assert "found 2" in _issues(hierarchy.SingleRoot(), chair)[0].message
    empty = scene_mod.SceneData("chair")
    empty.add_node(scene_mod.Node("|chair"))
    assert "geo" in _issues(hierarchy.SingleRoot(), empty)[0].message


def test_empty_groups_found_and_deleted(chair):
    chair.add_node(scene_mod.Node("|chair|geo|old_GRP"))
    chair.add_node(scene_mod.Node("|chair|geo|old_GRP|inner_GRP"))
    issues = _issues(hierarchy.EmptyGroups(), chair)
    assert [i.node for i in issues] == ["|chair|geo|old_GRP", "|chair|geo|old_GRP|inner_GRP"]
    assert _fix(hierarchy.EmptyGroups(), chair).fixed
    assert "|chair|geo|old_GRP" not in chair.nodes


def test_naming_convention_and_suffix_fix(chair):
    chair.rename(SEAT, "seat_LOD0")
    chair.rename("|chair|geo|LOD1|back_LOD1_GEO", "Back-Rest")
    issues = _issues(naming.NamingConvention(), chair)
    assert {i.data["rename"] for i in issues} == {"seat_LOD0_GEO", None}
    result = _fix(naming.NamingConvention(), chair)
    assert SEAT in chair.nodes
    assert not result.fixed and len(result.issues) == 1


def test_naming_root_must_match_asset(chair):
    chair.name = "table"
    issues = _issues(naming.NamingConvention(), chair)
    assert issues[0].data["rename"] == "table"


def test_naming_pattern_is_configurable(chair):
    config = {"naming.convention": {"mesh_pattern": r"^.*_MSH$"}}
    assert len(_issues(naming.NamingConvention(), chair, config)) == 6


def test_unique_names_and_fix(chair):
    chair.add_node(scene_mod.Node("|chair|geo|LOD1|extra_GRP"))
    chair.add_node(scene_mod.Node("|chair|geo|LOD1|extra_GRP|seat_LOD0_GEO",
                                  mesh=scenes.box(material="wood_MTL")))
    issues = _issues(naming.UniqueNames(), chair)
    assert [i.node for i in issues] == ["|chair|geo|LOD1|extra_GRP|seat_LOD0_GEO"]
    assert _fix(naming.UniqueNames(), chair).fixed
    assert "|chair|geo|LOD1|extra_GRP|seat_LOD0_01_GEO" in chair.nodes


def test_frozen_transforms_and_fix(chair):
    chair.get("|chair|geo").rotate = (0.0, 45.0, 0.0)
    chair.get(SEAT).translate = (1.0, 0.0, 0.0)
    issues = _issues(transforms.FrozenTransforms(), chair)
    assert [i.node for i in issues] == ["|chair|geo", SEAT]
    assert issues[0].data["attrs"] == ["rotate"]
    assert _fix(transforms.FrozenTransforms(), chair).fixed


def test_history_and_fix(chair):
    chair.get(SEAT).history = ["polyBevel3", "groupId"]
    issues = _issues(transforms.NoHistory(), chair)
    assert issues[0].data["history"] == ["polyBevel3"]
    assert _fix(transforms.NoHistory(), chair).fixed


def test_pivot_origin_and_bottom_center(chair):
    chair.get("|chair").pivot = (0.0, 45.0, 0.0)
    assert len(_issues(transforms.PivotPlacement(), chair)) == 1
    assert _fix(transforms.PivotPlacement(), chair).fixed

    config = {"transform.pivot": {"mode": "bottom_center"}}
    chair.get(SEAT).translate = (0.0, 10.0, 0.0)
    issues = _issues(transforms.PivotPlacement(), chair, config)
    assert issues == []  # bottom of the legs is still at y=0, centered
    chair.get("|chair").pivot = (0.0, 5.0, 0.0)
    issues = _issues(transforms.PivotPlacement(), chair, config)
    assert issues[0].data["target"] == pytest.approx([0.0, 0.0, 0.0])


def test_pivot_bad_mode_raises(chair):
    with pytest.raises(ValueError):
        _issues(transforms.PivotPlacement(), chair, {"transform.pivot": {"mode": "top"}})


def test_ngons(chair):
    mesh = chair.get(SEAT).mesh
    mesh.face_counts[:2] = [5, 3]
    issues = _issues(topology.NoNgons(), chair)
    assert issues[0].data["faces"] == [0]


def test_lamina_and_non_manifold(chair):
    mesh = chair.get(SEAT).mesh
    mesh.lamina_faces = [3]
    mesh.non_manifold_edges = [7, 8]
    issues = _issues(topology.CleanManifold(), chair)
    assert [sorted(i.data) for i in issues] == [["faces"], ["edges"]]


def test_uv_sets_present(chair):
    chair.get(SEAT).mesh.uv_sets = {}
    other = chair.get("|chair|geo|LOD0|back_LOD0_GEO").mesh
    other.uv_sets["extra"] = scene_mod.UVSet([(0, 0)], [0])
    messages = [i.message for i in _issues(uvs.UVSetsPresent(), chair)]
    assert messages == ["no UV sets", "UV set 'extra' does not cover every face-vertex"]


def test_uv_range_and_udim(chair):
    uv_set = chair.get(SEAT).mesh.uv_sets["map1"]
    uv_set.uvs[0] = (1.5, 0.2)
    uv_set.uvs[1] = (-0.5, 0.2)
    issues = _issues(uvs.UVRange(), chair)
    assert issues[0].data["count"] == 2
    config = {"uv.range": {"allow_udim": True}}
    assert _issues(uvs.UVRange(), chair, config)[0].data["count"] == 1


def test_material_assigned(chair):
    chair.get(SEAT).mesh.material = None
    chair.get("|chair|geo|LOD0|back_LOD0_GEO").mesh.material = "ghost_MTL"
    issues = _issues(materials.MaterialAssigned(), chair)
    assert [i.message for i in issues] == ["no material assigned", "unknown material 'ghost_MTL'"]


def test_textures_exist_with_relative_and_udim_paths(chair, tmp_path):
    (tmp_path / "tex").mkdir()
    (tmp_path / "tex" / "wood_rough.png").write_bytes(b"")
    (tmp_path / "tex" / "wood_color.1002.png").write_bytes(b"")
    chair.source_dir = str(tmp_path)
    chair.materials["wood_MTL"].textures = {
        "base_color": "tex/wood_color.<UDIM>.png",
        "roughness": str(tmp_path / "tex" / "wood_rough.png"),
        "normal": "tex/wood_normal.png",
    }
    issues = _issues(materials.TexturesExist(), chair)
    assert [i.data["slot"] for i in issues] == ["normal"]
    assert not materials.texture_exists("")


def test_poly_budget(chair):
    config = {"lod.budget": {"budgets": {"LOD0": 100}}}
    issues = _issues(lod.PolyBudget(), chair, config)
    assert issues[0].data == {"lod": "LOD0", "triangles": 576, "budget": 100}


def test_poly_budget_requires_decreasing_lods(chair):
    for node in chair.descendants("|chair|geo|LOD1"):
        if node.mesh:
            node.mesh = scenes.box(divisions=5, material="wood_MTL")
    issues = _issues(lod.PolyBudget(), chair)
    assert "not lighter than LOD0" in issues[0].message


def test_lod_consistency(chair):
    chair.rename("|chair|geo|LOD1|back_LOD1_GEO", "back_LOD0_GEO2")
    chair.remove("|chair|geo|LOD1|legs_LOD1_GEO")
    chair.rename("|chair|geo|LOD1", "LOD2")
    messages = [i.message for i in _issues(lod.LODConsistency(), chair)]
    assert any("not numbered" in m for m in messages)
    assert any("_LOD2" in m for m in messages)
    assert any("missing parts" in m for m in messages)
    assert any("parts not in LOD0" in m for m in messages)


def test_lod_consistency_ignores_single_lod(chair):
    chair.remove("|chair|geo|LOD1")
    assert _issues(lod.LODConsistency(), chair) == []
