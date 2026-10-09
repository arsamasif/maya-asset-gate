"""Naming checks: convention per node kind and unique short names.

Names are judged by node kind (root, group, mesh), each with its own
configurable regex. Fixes only do safe, mechanical renames such as adding
a missing suffix or numbering a duplicate.

"""

import re
from collections import defaultdict

from asset_gate import check


class NamingConvention(check.BaseCheck):
    """Node names must match the configured regex for their kind."""

    id = "naming.convention"
    label = "Naming convention"
    category = "naming"
    order = 10
    description = "Root, group and mesh names follow the studio regexes."
    defaults = {
        "root_pattern": r"^[a-z][A-Za-z0-9]*$",
        "group_pattern": r"^(geo|proxy|LOD[0-9]+|[a-z][A-Za-z0-9]*(_[A-Za-z0-9]+)*_GRP)$",
        "mesh_pattern": r"^[a-z][A-Za-z0-9]*(_[A-Za-z0-9]+)*_GEO$",
        "group_suffix": "_GRP",
        "mesh_suffix": "_GEO",
    }

    def run(self, context):
        options = self.options(context)
        scene = context.scene
        issues = []
        for node in scene.nodes.values():
            kind = _kind(node)
            pattern = re.compile(options[kind + "_pattern"])
            if not pattern.match(node.name):
                issues.append(check.Issue(
                    "{0} name does not match {1}".format(kind, pattern.pattern),
                    node.path,
                    {"kind": kind, "rename": self._suggest(node.name, kind, options)},
                ))
            elif kind == "root" and node.name != scene.name:
                issues.append(check.Issue(
                    "root is named {0!r} but the asset is {1!r}".format(node.name, scene.name),
                    node.path,
                    {"kind": kind, "rename": scene.name},
                ))
        return issues

    def fix(self, context, issues):
        # Deepest first, so renaming a child never invalidates a parent path.
        for issue in sorted(issues, key=lambda i: i.node.count("|"), reverse=True):
            new_name = issue.data.get("rename")
            if new_name:
                context.editor.rename(issue.node, new_name)

    @staticmethod
    def _suggest(name, kind, options):
        suffix = options.get(kind + "_suffix")
        if not suffix or name.endswith(suffix):
            return None
        candidate = name + suffix
        if re.match(options[kind + "_pattern"], candidate):
            return candidate
        return None


class UniqueNames(check.BaseCheck):
    """Short names must be unique so Maya and USD paths stay unambiguous."""

    id = "naming.unique"
    label = "Unique short names"
    category = "naming"
    order = 20
    description = "No two nodes share a short name anywhere in the asset."

    def run(self, context):
        by_name = defaultdict(list)
        for node in context.scene.nodes.values():
            by_name[node.name].append(node.path)
        issues = []
        for name, paths in by_name.items():
            for path in paths[1:]:
                issues.append(check.Issue(
                    "short name {0!r} also used by {1}".format(name, paths[0]), path))
        return issues

    def fix(self, context, issues):
        taken = {node.name for node in context.scene.nodes.values()}
        for issue in sorted(issues, key=lambda i: i.node.count("|"), reverse=True):
            name = issue.node.rsplit("|", 1)[-1]
            new_name = _numbered(name, taken)
            taken.add(new_name)
            context.editor.rename(issue.node, new_name)


def _kind(node):
    if not node.parent_path:
        return "root"
    return "mesh" if node.mesh is not None else "group"


def _numbered(name, taken):
    head, sep, tail = name.rpartition("_")
    if not sep:
        head, tail = name, ""
    index = 1
    while True:
        candidate = "{0}{1}{2:02d}{3}".format(head, "_" if head else "", index,
                                               "_" + tail if tail else "")
        if candidate not in taken:
            return candidate
        index += 1
