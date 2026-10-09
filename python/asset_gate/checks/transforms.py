"""Transform checks: frozen transforms, construction history and pivots.

These are the classic "clean scene" rules. Each one has a fix that maps to
a single Maya command (makeIdentity, delete -ch, xform -piv), applied
through the context's editor.

"""

import math

from asset_gate import check

TOLERANCE = 1e-5
IDENTITY_VALUES = {"translate": 0.0, "rotate": 0.0, "scale": 1.0}


class FrozenTransforms(check.BaseCheck):
    """Every transform must be frozen (zero translate/rotate, unit scale)."""

    id = "transform.frozen"
    label = "Frozen transforms"
    category = "transform"
    order = 10
    description = "Translate, rotate and scale are at identity on all nodes."
    defaults = {"tolerance": TOLERANCE}

    def run(self, context):
        tolerance = self.options(context)["tolerance"]
        issues = []
        for node in context.scene.nodes.values():
            dirty = [
                attr for attr, rest in IDENTITY_VALUES.items()
                if any(abs(value - rest) > tolerance for value in getattr(node, attr))
            ]
            if dirty:
                issues.append(check.Issue(
                    "non-identity {0}".format(", ".join(dirty)), node.path, {"attrs": dirty}))
        return issues

    def fix(self, context, issues):
        # Freezing a node also freezes its children, so only freeze the top-most ones.
        paths = sorted(issue.node for issue in issues)
        frozen = []
        for path in paths:
            if any(path.startswith(parent + "|") for parent in frozen):
                continue
            context.editor.freeze_transforms(path)
            frozen.append(path)


class NoHistory(check.BaseCheck):
    """Meshes must not carry construction history."""

    id = "transform.history"
    label = "No construction history"
    category = "transform"
    order = 20
    description = "No upstream modelling nodes are left on any shape."
    defaults = {"ignore_types": ["groupId", "shadingEngine"]}

    def run(self, context):
        ignored = set(self.options(context)["ignore_types"])
        issues = []
        for node in context.scene.nodes.values():
            history = [kind for kind in node.history if kind not in ignored]
            if history:
                issues.append(check.Issue(
                    "history: {0}".format(", ".join(history)), node.path, {"history": history}))
        return issues

    def fix(self, context, issues):
        for issue in issues:
            context.editor.delete_history(issue.node)


class PivotPlacement(check.BaseCheck):
    """The root pivot must sit at the origin or at the asset's bottom center."""

    id = "transform.pivot"
    label = "Pivot placement"
    category = "transform"
    order = 30
    description = "Root pivot at the world origin (or bottom center, if configured)."
    defaults = {"mode": "origin", "scope": "root", "tolerance": 1e-3}

    def run(self, context):
        options = self.options(context)
        if options["mode"] not in ("origin", "bottom_center"):
            raise ValueError("Unknown pivot mode: {0}".format(options["mode"]))
        scene = context.scene
        nodes = [scene.root()] if options["scope"] == "root" else list(scene.nodes.values())
        issues = []
        for node in nodes:
            target = self._target(scene, node.path, options["mode"])
            if target is None:
                continue
            if math.dist(node.pivot, target) > options["tolerance"]:
                issues.append(check.Issue(
                    "pivot {0} should be at {1}".format(_fmt(node.pivot), _fmt(target)),
                    node.path,
                    {"target": list(target)},
                ))
        return issues

    def fix(self, context, issues):
        for issue in issues:
            context.editor.set_pivot(issue.node, issue.data["target"])

    @staticmethod
    def _target(scene, path, mode):
        if mode == "origin":
            return (0.0, 0.0, 0.0)
        bounds = scene.world_bounds(path)
        if bounds is None:
            return None
        lower, upper = bounds
        return ((lower[0] + upper[0]) / 2.0, lower[1], (lower[2] + upper[2]) / 2.0)


def _fmt(point):
    return "({0})".format(", ".join("{0:.3f}".format(v) for v in point))
