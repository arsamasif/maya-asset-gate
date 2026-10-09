"""UV checks: every mesh has a usable UV set, and UVs stay in 0-1.

The range check is a warning by default because UDIM assets legitimately
leave the 0-1 tile; set ``allow_udim`` to accept any positive tile.

"""

from asset_gate import check


class UVSetsPresent(check.BaseCheck):
    """Each mesh needs at least one UV set that covers every face-vertex."""

    id = "uv.present"
    label = "UV sets present"
    category = "uv"
    order = 10
    description = "Meshes have a UV set, the default one is named as configured."
    defaults = {"default_set": "map1"}

    def run(self, context):
        default_set = self.options(context)["default_set"]
        issues = []
        for node in context.scene.mesh_nodes():
            mesh = node.mesh
            if not mesh.uv_sets:
                issues.append(check.Issue("no UV sets", node.path))
                continue
            if default_set and default_set not in mesh.uv_sets:
                issues.append(check.Issue(
                    "missing default UV set {0!r}".format(default_set), node.path))
            for name, uv_set in mesh.uv_sets.items():
                if not uv_set.uvs or len(uv_set.indices) != len(mesh.face_indices):
                    issues.append(check.Issue(
                        "UV set {0!r} does not cover every face-vertex".format(name),
                        node.path, {"uv_set": name}))
        return issues


class UVRange(check.BaseCheck):
    """UVs must lie in the 0-1 tile (or in positive UDIM tiles if allowed)."""

    id = "uv.range"
    label = "UVs inside 0-1"
    category = "uv"
    severity = check.WARNING
    order = 20
    description = "No UV coordinate falls outside the allowed tile range."
    defaults = {"allow_udim": False, "tolerance": 1e-4}

    def run(self, context):
        options = self.options(context)
        tolerance = options["tolerance"]
        upper = float("inf") if options["allow_udim"] else 1.0 + tolerance
        issues = []
        for node in context.scene.mesh_nodes():
            for name, uv_set in node.mesh.uv_sets.items():
                outside = sum(
                    1 for u, v in uv_set.uvs
                    if not (-tolerance <= u <= upper and -tolerance <= v <= upper)
                )
                if outside:
                    issues.append(check.Issue(
                        "{0} UVs outside range in set {1!r}".format(outside, name),
                        node.path, {"uv_set": name, "count": outside}))
        return issues
