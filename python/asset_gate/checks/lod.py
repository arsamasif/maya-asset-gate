"""LOD checks: triangle budgets per level and consistent LOD naming.

Both checks rely on ``asset_gate.layout`` to decide which LOD a mesh
belongs to, the same grouping the USD publisher turns into a variant set.

"""

from asset_gate import check
from asset_gate import layout


class PolyBudget(check.BaseCheck):
    """Each LOD stays under its triangle budget and is lighter than the last."""

    id = "lod.budget"
    label = "Poly budget per LOD"
    category = "lod"
    order = 10
    description = "Triangle counts per LOD are within budget and decreasing."
    defaults = {
        "budgets": {"LOD0": 50000, "LOD1": 20000, "LOD2": 8000, "LOD3": 3000},
        "default_budget": None,
        "require_decreasing": True,
    }

    def run(self, context):
        options = self.options(context)
        issues = []
        previous = None
        for lod, nodes in layout.meshes_by_lod(context.scene).items():
            triangles = sum(node.mesh.triangle_count for node in nodes)
            budget = options["budgets"].get(lod, options["default_budget"])
            if budget is not None and triangles > budget:
                issues.append(check.Issue(
                    "{0} has {1} triangles, budget is {2}".format(lod, triangles, budget),
                    "", {"lod": lod, "triangles": triangles, "budget": budget}))
            if options["require_decreasing"] and previous and triangles >= previous[1]:
                issues.append(check.Issue(
                    "{0} ({1} tris) is not lighter than {2} ({3} tris)".format(
                        lod, triangles, previous[0], previous[1]),
                    "", {"lod": lod, "triangles": triangles}))
            previous = (lod, triangles)
        return issues


class LODConsistency(check.BaseCheck):
    """LOD groups are numbered from 0 and contain the same named parts."""

    id = "lod.consistency"
    label = "LOD naming consistency"
    category = "lod"
    severity = check.WARNING
    order = 20
    description = "LOD tokens match their group and every LOD has the same parts."
    defaults = {"require_matching_parts": True}

    def run(self, context):
        grouped = layout.meshes_by_lod(context.scene)
        if len(grouped) < 2:
            return []
        issues = []
        expected = ["LOD{0}".format(i) for i in range(len(grouped))]
        if list(grouped) != expected:
            issues.append(check.Issue(
                "LOD groups {0} are not numbered {1}".format(list(grouped), expected)))
        for lod, nodes in grouped.items():
            for node in nodes:
                tokens = layout.LOD_TOKEN_RE.findall(node.name)
                if tokens != [str(layout.lod_index(lod))]:
                    issues.append(check.Issue(
                        "name should carry the token _{0}".format(lod), node.path,
                        {"lod": lod}))
        if self.options(context)["require_matching_parts"]:
            issues.extend(self._part_issues(grouped))
        return issues

    @staticmethod
    def _part_issues(grouped):
        parts = {
            lod: {layout.base_name(node.name) for node in nodes}
            for lod, nodes in grouped.items()
        }
        reference_lod = next(iter(parts))
        reference = parts[reference_lod]
        issues = []
        for lod, names in parts.items():
            missing = sorted(reference - names)
            extra = sorted(names - reference)
            if missing:
                issues.append(check.Issue(
                    "{0} is missing parts {1}".format(lod, missing), "", {"lod": lod}))
            if extra:
                issues.append(check.Issue(
                    "{0} has parts not in {1}: {2}".format(lod, reference_lod, extra), "",
                    {"lod": lod}))
        return issues
