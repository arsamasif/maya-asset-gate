"""Tests for the USD publish: open the result with pxr and inspect it.

"""

import os

import pytest
from pxr import Kind, Sdf, Usd, UsdGeom, UsdShade

from asset_gate import scene as scene_mod
from asset_gate import usd_publish
from asset_gate.test import scenes


@pytest.fixture
def published(tmp_path):
    scene = scenes.chair_scene()
    (tmp_path / "src" / "tex").mkdir(parents=True)
    scene.source_dir = str(tmp_path / "src")
    scene.materials["wood_MTL"].textures = {
        "base_color": "tex/wood_color.<UDIM>.png",
        "normal": "tex/wood_normal.png",
    }
    result = usd_publish.publish(scene, str(tmp_path / "out"))
    return scene, result


def _open(path, load=Usd.Stage.LoadAll):
    stage = Usd.Stage.Open(path, load)
    assert stage, path
    return stage


def test_layer_files_and_layout(published):
    _, result = published
    for path in (result.asset, result.payload, result.geo, result.mtl):
        assert os.path.isfile(path)
    assert os.path.basename(result.asset) == "chair.usda"
    payload_layer = Sdf.Layer.FindOrOpen(result.payload)
    assert list(payload_layer.subLayerPaths) == ["./geo.usda", "./mtl.usda"]
    asset_layer = Sdf.Layer.FindOrOpen(result.asset)
    root_spec = asset_layer.GetPrimAtPath("/chair")
    assert [p.assetPath for p in root_spec.payloadList.prependedItems] == ["./payload.usda"]


def test_root_kind_metadata_and_stage_settings(published):
    _, result = published
    stage = _open(result.asset, Usd.Stage.LoadNone)
    root = stage.GetDefaultPrim()
    assert root.GetPath() == Sdf.Path("/chair")
    assert root.IsA(UsdGeom.Xform)
    model = Usd.ModelAPI(root)
    assert model.GetKind() == Kind.Tokens.component
    assert model.GetAssetName() == "chair"
    assert model.GetAssetVersion() == "3"
    assert model.GetAssetIdentifier().path == "./chair.usda"
    assert UsdGeom.GetStageUpAxis(stage) == UsdGeom.Tokens.y
    assert UsdGeom.GetStageMetersPerUnit(stage) == pytest.approx(0.01)
    # With payloads unloaded no geometry is composed, but the LOD choice is visible.
    assert not stage.GetPrimAtPath("/chair/geo")
    assert root.GetVariantSets().GetVariantSet("lod").GetVariantNames() == ["LOD0", "LOD1"]


def test_purposes_and_proxy(published):
    _, result = published
    stage = _open(result.asset)
    render = UsdGeom.Imageable(stage.GetPrimAtPath("/chair/geo/render"))
    proxy = UsdGeom.Imageable(stage.GetPrimAtPath("/chair/geo/proxy"))
    assert render.GetPurposeAttr().Get() == UsdGeom.Tokens.render
    assert proxy.GetPurposeAttr().Get() == UsdGeom.Tokens.proxy
    assert render.GetProxyPrimRel().GetTargets() == [Sdf.Path("/chair/geo/proxy")]
    box = UsdGeom.Mesh(stage.GetPrimAtPath("/chair/geo/proxy/bbox"))
    lower, upper = box.GetExtentAttr().Get()
    assert tuple(lower) == pytest.approx((-20.0, 0.0, -20.0))
    assert tuple(upper) == pytest.approx((20.0, 97.5, 20.0))


def test_lod_variants_switch_geometry(published):
    scene, result = published
    stage = _open(result.asset)
    root = stage.GetDefaultPrim()
    lod_set = root.GetVariantSets().GetVariantSet("lod")
    assert lod_set.GetVariantSelection() == "LOD0"
    render = stage.GetPrimAtPath("/chair/geo/render")
    assert [p.GetName() for p in render.GetChildren()] == [
        "seat_LOD0_GEO", "back_LOD0_GEO", "legs_LOD0_GEO"]
    seat = UsdGeom.Mesh(render.GetChild("seat_LOD0_GEO"))
    source = scene.get("|chair|geo|LOD0|seat_LOD0_GEO").mesh
    assert len(seat.GetFaceVertexCountsAttr().Get()) == source.face_count
    assert seat.GetSubdivisionSchemeAttr().Get() == UsdGeom.Tokens.none

    lod_set.SetVariantSelection("LOD1")
    assert [p.GetName() for p in render.GetChildren()] == [
        "seat_LOD1_GEO", "back_LOD1_GEO", "legs_LOD1_GEO"]


def test_uv_primvar(published):
    _, result = published
    stage = _open(result.asset)
    mesh = stage.GetPrimAtPath("/chair/geo/render/seat_LOD0_GEO")
    primvar = UsdGeom.PrimvarsAPI(mesh).GetPrimvar("st")
    assert primvar.GetInterpolation() == UsdGeom.Tokens.faceVarying
    assert primvar.IsIndexed()
    assert len(primvar.GetIndices()) == len(UsdGeom.Mesh(mesh).GetFaceVertexIndicesAttr().Get())


def test_materials_and_bindings(published, tmp_path):
    _, result = published
    stage = _open(result.asset)
    seat = stage.GetPrimAtPath("/chair/geo/render/seat_LOD0_GEO")
    material, _ = UsdShade.MaterialBindingAPI(seat).ComputeBoundMaterial()
    assert material.GetPath() == Sdf.Path("/chair/mtl/wood_MTL")

    surface = material.ComputeSurfaceSource()[0]
    assert surface.GetIdAttr().Get() == "UsdPreviewSurface"
    assert surface.GetInput("roughness").Get() == pytest.approx(0.6)

    diffuse_source = surface.GetInput("diffuseColor").GetConnectedSources()[0][0]
    texture = UsdShade.Shader(diffuse_source.source.GetPrim())
    assert texture.GetIdAttr().Get() == "UsdUVTexture"
    assert texture.GetInput("file").Get().path == "../src/tex/wood_color.<UDIM>.png"
    assert texture.GetInput("sourceColorSpace").Get() == "sRGB"
    normal = stage.GetPrimAtPath("/chair/mtl/wood_MTL/normalTex")
    assert UsdShade.Shader(normal).GetInput("sourceColorSpace").Get() == "raw"


def test_explicit_proxy_meshes_and_transforms(tmp_path):
    scene = scenes.chair_scene()
    scene.add_node(scene_mod.Node("|chair|geo|proxy"))
    scene.add_node(scene_mod.Node("|chair|geo|proxy|chair_proxy_GEO", mesh=scenes.box()))
    scene.get("|chair|geo|LOD0|seat_LOD0_GEO").translate = (0.0, 2.0, 0.0)
    result = usd_publish.publish(scene, str(tmp_path))
    stage = _open(result.asset)
    assert stage.GetPrimAtPath("/chair/geo/proxy/chair_proxy_GEO").IsA(UsdGeom.Mesh)
    assert not stage.GetPrimAtPath("/chair/geo/proxy/bbox")
    seat = UsdGeom.Xformable(stage.GetPrimAtPath("/chair/geo/render/seat_LOD0_GEO"))
    matrix = seat.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    assert tuple(matrix.ExtractTranslation()) == pytest.approx((0.0, 2.0, 0.0))


def test_republish_overwrites(tmp_path):
    scene = scenes.chair_scene()
    usd_publish.publish(scene, str(tmp_path))
    scene.version = 4
    result = usd_publish.publish(scene, str(tmp_path))
    assert "4" in open(result.asset).read()


def test_publish_without_meshes_raises(tmp_path):
    scene = scene_mod.SceneData("empty")
    scene.add_node(scene_mod.Node("|empty"))
    with pytest.raises(ValueError):
        usd_publish.publish(scene, str(tmp_path))


def test_prim_name_sanitizes():
    assert usd_publish.prim_name("ns:wood-MTL") == "wood_MTL"
