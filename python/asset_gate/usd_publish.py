"""Write a SceneData asset as a payload-friendly USD asset.

The output folder holds four layers::

    <asset>.usda   entry point: root Xform, kind=component, assetInfo,
                   payload -> payload.usda, default LOD selection
    payload.usda   sublayers geo.usda and mtl.usda
    geo.usda       /<asset>/geo/render (purpose=render) inside a "lod"
                   variant set, /<asset>/geo/proxy (purpose=proxy)
    mtl.usda       /<asset>/mtl with one UsdPreviewSurface material each

Opening the entry layer with payloads unloaded gives a cheap stage with the
asset's kind, metadata and variant selection; loading the payload brings in
geometry and materials. Geometry is written from the SceneData mesh arrays,
so this runs anywhere usd-core is installed.

"""

import os
from dataclasses import dataclass

from pxr import Gf, Kind, Sdf, Tf, Usd, UsdGeom, UsdShade, Vt

from asset_gate import layout
from asset_gate import xform
from asset_gate.checks import materials as materials_check

GEO_LAYER = "geo.usda"
MTL_LAYER = "mtl.usda"
PAYLOAD_LAYER = "payload.usda"
LOD_VARIANT_SET = "lod"
MTL_SCOPE = "mtl"
DEFAULT_UV_SET = "map1"
PROXY_COLOR = (0.45, 0.45, 0.5)
TEXTURE_INPUTS = {
    # slot: (PreviewSurface input, its type, texture output, its type)
    "base_color": ("diffuseColor", Sdf.ValueTypeNames.Color3f, "rgb", Sdf.ValueTypeNames.Float3),
    "roughness": ("roughness", Sdf.ValueTypeNames.Float, "r", Sdf.ValueTypeNames.Float),
    "metallic": ("metallic", Sdf.ValueTypeNames.Float, "r", Sdf.ValueTypeNames.Float),
    "normal": ("normal", Sdf.ValueTypeNames.Normal3f, "rgb", Sdf.ValueTypeNames.Float3),
}
BOX_FACES = (
    (0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1),
    (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3),
)


@dataclass
class PublishResult:
    """Paths of the layers written by ``publish``."""

    asset: str
    payload: str
    geo: str
    mtl: str


def publish(scene, out_dir, meters_per_unit=0.01, up_axis="Y"):
    """Write the asset layers for ``scene`` into ``out_dir``.

    Args:
        scene (SceneData): Validated scene to publish.
        out_dir (str): Destination folder (created if needed).
        meters_per_unit (float): Stage units; Maya works in centimeters.
        up_axis (str): ``"Y"`` or ``"Z"``.

    Returns:
        PublishResult: Paths of the written layers.

    Raises:
        ValueError: If the scene has no render geometry.

    """
    lods = layout.meshes_by_lod(scene)
    if not lods:
        raise ValueError("Scene {0!r} has no render meshes to publish".format(scene.name))
    os.makedirs(out_dir, exist_ok=True)
    root_name = prim_name(scene.name)
    settings = {"root": root_name, "meters_per_unit": meters_per_unit, "up_axis": up_axis}
    result = PublishResult(
        asset=os.path.join(out_dir, scene.name + ".usda"),
        payload=os.path.join(out_dir, PAYLOAD_LAYER),
        geo=os.path.join(out_dir, GEO_LAYER),
        mtl=os.path.join(out_dir, MTL_LAYER),
    )
    _write_mtl_layer(scene, result.mtl, out_dir, settings)
    _write_geo_layer(scene, lods, result.geo, settings)
    _write_payload_layer(result.payload, settings)
    _write_asset_layer(scene, list(lods), result.asset, settings)
    return result


def prim_name(name):
    """Turn a Maya node or material name into a valid USD prim name.

    Args:
        name (str): Source name (may contain namespaces or dashes).

    Returns:
        str: A valid identifier.

    """
    return Tf.MakeValidIdentifier(name.rsplit(":", 1)[-1])


# -- layers ---------------------------------------------------------------


def _new_stage(path, settings):
    if os.path.exists(path):
        os.remove(path)
    stage = Usd.Stage.CreateNew(path)
    UsdGeom.SetStageMetersPerUnit(stage, settings["meters_per_unit"])
    UsdGeom.SetStageUpAxis(stage, settings["up_axis"])
    stage.SetDefaultPrim(stage.DefinePrim("/" + settings["root"], "Xform"))
    return stage


def _write_asset_layer(scene, lod_names, path, settings):
    stage = _new_stage(path, settings)
    root = stage.GetDefaultPrim()
    Usd.ModelAPI(root).SetKind(Kind.Tokens.component)
    model = Usd.ModelAPI(root)
    model.SetAssetName(scene.name)
    model.SetAssetVersion(str(scene.version))
    model.SetAssetIdentifier(Sdf.AssetPath("./" + os.path.basename(path)))
    root.GetPayloads().AddPayload("./" + PAYLOAD_LAYER)
    variant_set = root.GetVariantSets().AddVariantSet(LOD_VARIANT_SET)
    for lod in lod_names:
        variant_set.AddVariant(lod)
    variant_set.SetVariantSelection(lod_names[0])
    stage.GetRootLayer().documentation = "Asset {0} v{1}".format(scene.name, scene.version)
    stage.Save()


def _write_payload_layer(path, settings):
    stage = _new_stage(path, settings)
    stage.GetRootLayer().subLayerPaths = ["./" + GEO_LAYER, "./" + MTL_LAYER]
    stage.Save()


def _write_geo_layer(scene, lods, path, settings):
    stage = _new_stage(path, settings)
    root = stage.GetDefaultPrim()
    geo_path = root.GetPath().AppendChild(layout.GEO_GROUP)
    UsdGeom.Xform.Define(stage, geo_path)
    render = UsdGeom.Xform.Define(stage, geo_path.AppendChild("render"))
    render.CreatePurposeAttr(UsdGeom.Tokens.render)
    proxy = UsdGeom.Xform.Define(stage, geo_path.AppendChild("proxy"))
    proxy.CreatePurposeAttr(UsdGeom.Tokens.proxy)
    render.SetProxyPrim(proxy.GetPrim())

    mtl_path = root.GetPath().AppendChild(MTL_SCOPE)
    variant_set = root.GetVariantSets().AddVariantSet(LOD_VARIANT_SET)
    for lod, nodes in lods.items():
        variant_set.AddVariant(lod)
        variant_set.SetVariantSelection(lod)
        with variant_set.GetVariantEditContext():
            _write_meshes(stage, scene, nodes, render.GetPath(), mtl_path)
    variant_set.SetVariantSelection(next(iter(lods)))

    proxies = layout.proxy_meshes(scene)
    if proxies:
        _write_meshes(stage, scene, proxies, proxy.GetPath(), None)
    else:
        bounds = None
        for node in next(iter(lods.values())):
            bounds = _union(bounds, scene.world_bounds(node.path))
        if bounds is not None:
            _write_box(stage, proxy.GetPath().AppendChild("bbox"), bounds)
    stage.Save()


def _write_mtl_layer(scene, path, out_dir, settings):
    stage = _new_stage(path, settings)
    scope_path = stage.GetDefaultPrim().GetPath().AppendChild(MTL_SCOPE)
    UsdGeom.Scope.Define(stage, scope_path)
    for material in scene.materials.values():
        _write_material(stage, scope_path, material, scene.source_dir, out_dir)
    stage.Save()


# -- geometry -------------------------------------------------------------


def _write_meshes(stage, scene, nodes, parent_path, mtl_path):
    used = set()
    for node in nodes:
        name = _unique(prim_name(node.name), used)
        mesh = node.mesh
        usd_mesh = UsdGeom.Mesh.Define(stage, parent_path.AppendChild(name))
        points = Vt.Vec3fArray([Gf.Vec3f(*p) for p in mesh.points])
        usd_mesh.CreatePointsAttr(points)
        usd_mesh.CreateFaceVertexCountsAttr(Vt.IntArray(mesh.face_counts))
        usd_mesh.CreateFaceVertexIndicesAttr(Vt.IntArray(mesh.face_indices))
        usd_mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
        usd_mesh.CreateExtentAttr(UsdGeom.Mesh.ComputeExtent(points))
        matrix = scene.world_matrix(node.path)
        if not xform.is_identity(matrix):
            usd_mesh.MakeMatrixXform().Set(Gf.Matrix4d(matrix))
        _write_uvs(usd_mesh, mesh)
        material = scene.materials.get(mesh.material) if mesh.material else None
        if material is not None:
            usd_mesh.CreateDisplayColorAttr([Gf.Vec3f(*material.base_color)])
            if mtl_path is not None:
                _bind(usd_mesh.GetPrim(), mtl_path.AppendChild(prim_name(material.name)))


def _write_uvs(usd_mesh, mesh):
    primvars = UsdGeom.PrimvarsAPI(usd_mesh)
    names = sorted(mesh.uv_sets, key=lambda n: (n != DEFAULT_UV_SET, n))
    for position, set_name in enumerate(names):
        uv_set = mesh.uv_sets[set_name]
        if not uv_set.uvs or len(uv_set.indices) != len(mesh.face_indices):
            continue
        primvar_name = "st" if position == 0 else "st_" + prim_name(set_name)
        primvar = primvars.CreatePrimvar(
            primvar_name, Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.faceVarying)
        primvar.Set(Vt.Vec2fArray([Gf.Vec2f(*uv) for uv in uv_set.uvs]))
        primvar.SetIndices(Vt.IntArray(uv_set.indices))


def _bind(prim, material_path):
    # The material lives in mtl.usda, so bind by path instead of by UsdShade.Material.
    UsdShade.MaterialBindingAPI.Apply(prim)
    prim.CreateRelationship(UsdShade.Tokens.materialBinding).SetTargets([material_path])


def _write_box(stage, path, bounds):
    (x0, y0, z0), (x1, y1, z1) = bounds
    points = Vt.Vec3fArray([
        Gf.Vec3f(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)
    ])
    box = UsdGeom.Mesh.Define(stage, path)
    box.CreatePointsAttr(points)
    box.CreateFaceVertexCountsAttr(Vt.IntArray([4] * len(BOX_FACES)))
    box.CreateFaceVertexIndicesAttr(Vt.IntArray([i for face in BOX_FACES for i in face]))
    box.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    box.CreateExtentAttr(UsdGeom.Mesh.ComputeExtent(points))
    box.CreateDisplayColorAttr([Gf.Vec3f(*PROXY_COLOR)])


def _union(a, b):
    if a is None or b is None:
        return a or b
    return (
        tuple(min(a[0][i], b[0][i]) for i in range(3)),
        tuple(max(a[1][i], b[1][i]) for i in range(3)),
    )


def _unique(name, used):
    candidate, index = name, 1
    while candidate in used:
        candidate = "{0}_{1}".format(name, index)
        index += 1
    used.add(candidate)
    return candidate


# -- materials ------------------------------------------------------------


def _write_material(stage, scope_path, material, source_dir, out_dir):
    usd_material = UsdShade.Material.Define(stage, scope_path.AppendChild(prim_name(material.name)))
    surface = UsdShade.Shader.Define(stage, usd_material.GetPath().AppendChild("PreviewSurface"))
    surface.CreateIdAttr("UsdPreviewSurface")
    surface.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(*material.base_color))
    surface.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(material.roughness)
    surface.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(material.metallic)
    usd_material.CreateSurfaceOutput().ConnectToSource(
        surface.ConnectableAPI(), "surface")

    if not material.textures:
        return
    reader = UsdShade.Shader.Define(stage, usd_material.GetPath().AppendChild("stReader"))
    reader.CreateIdAttr("UsdPrimvarReader_float2")
    reader.CreateInput("varname", Sdf.ValueTypeNames.String).Set("st")
    st_output = reader.CreateOutput("result", Sdf.ValueTypeNames.Float2)
    for slot, path in sorted(material.textures.items()):
        _write_texture(stage, usd_material, surface, st_output, slot,
                       _texture_path(path, source_dir, out_dir))


def _write_texture(stage, usd_material, surface, st_output, slot, file_path):
    surface_input, input_type, output_name, output_type = TEXTURE_INPUTS[slot]
    texture = UsdShade.Shader.Define(
        stage, usd_material.GetPath().AppendChild(_camel(slot) + "Tex"))
    texture.CreateIdAttr("UsdUVTexture")
    texture.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(file_path))
    texture.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(st_output)
    color_space = "sRGB" if slot == "base_color" else "raw"
    texture.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set(color_space)
    if slot == "normal":
        texture.CreateInput("scale", Sdf.ValueTypeNames.Float4).Set(Gf.Vec4f(2, 2, 2, 1))
        texture.CreateInput("bias", Sdf.ValueTypeNames.Float4).Set(Gf.Vec4f(-1, -1, -1, 0))
    output = texture.CreateOutput(output_name, output_type)
    surface.CreateInput(surface_input, input_type).ConnectToSource(output)


def _camel(slot):
    head, *rest = slot.split("_")
    return head + "".join(word.title() for word in rest)


def _texture_path(path, source_dir, out_dir):
    resolved = materials_check.resolve_texture(path, source_dir)
    if not os.path.isabs(resolved):
        return resolved.replace(os.sep, "/")
    try:
        relative = os.path.relpath(resolved, os.path.abspath(out_dir))
    except ValueError:
        # Different drives on Windows: keep the absolute path.
        return resolved.replace(os.sep, "/")
    relative = relative.replace(os.sep, "/")
    return relative if relative.startswith("../") else "./" + relative
