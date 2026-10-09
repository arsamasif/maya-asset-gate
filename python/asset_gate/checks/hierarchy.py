"""Hierarchy checks: one asset root and no empty groups.

A publishable asset has exactly one top-level node, named after the asset,
with a ``geo`` group under it. Empty groups are clutter that ends up as
empty prims in USD, so they can be deleted automatically.

"""

from asset_gate import check
from asset_gate import layout


class SingleRoot(check.BaseCheck):
    """The scene has one top-level node with a ``geo`` group below it."""

    id = "scene.root"
    label = "Single asset root"
    category = "scene"
    order = 10
    description = "Exactly one root transform, containing a geo group."

    def run(self, context):
        roots = context.scene.roots()
        if len(roots) != 1:
            return [check.Issue(
                "expected one root node, found {0}".format(len(roots)), "",
                {"roots": [node.path for node in roots]})]
        root = roots[0]
        geo_path = root.path + "|" + layout.GEO_GROUP
        if geo_path not in context.scene.nodes:
            return [check.Issue("missing group {0!r}".format(layout.GEO_GROUP), root.path)]
        if not context.scene.mesh_nodes():
            return [check.Issue("asset contains no meshes", root.path)]
        return []


class EmptyGroups(check.BaseCheck):
    """Groups must contain at least one mesh somewhere below them."""

    id = "scene.empty_groups"
    label = "No empty groups"
    category = "scene"
    severity = check.WARNING
    order = 20
    description = "Transforms without any mesh below them are removed."

    def run(self, context):
        scene = context.scene
        issues = []
        for node in scene.nodes.values():
            if node.mesh is not None or not node.parent_path:
                continue
            if not any(child.mesh is not None for child in scene.descendants(node.path)):
                issues.append(check.Issue("group has no meshes", node.path))
        return issues

    def fix(self, context, issues):
        deleted = []
        for path in sorted(issue.node for issue in issues):
            if any(path.startswith(parent + "|") for parent in deleted):
                continue
            context.editor.delete(path)
            deleted.append(path)
