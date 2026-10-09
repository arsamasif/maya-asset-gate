"""Topology checks: n-gons, lamina faces and non-manifold geometry.

N-gons are found from the face arrays directly. Lamina faces and
non-manifold edges need Maya's own analysis (``polyInfo``), so the adapter
stores their indices on the mesh and these checks only report them.

"""

from asset_gate import check

MAX_LISTED = 10


class NoNgons(check.BaseCheck):
    """Faces may have at most four vertices."""

    id = "topology.ngons"
    label = "No n-gons"
    category = "topology"
    order = 10
    description = "Every polygon is a triangle or a quad."
    defaults = {"max_vertices": 4}

    def run(self, context):
        limit = self.options(context)["max_vertices"]
        issues = []
        for node in context.scene.mesh_nodes():
            faces = [i for i, count in enumerate(node.mesh.face_counts) if count > limit]
            if faces:
                issues.append(check.Issue(
                    "{0} faces with more than {1} vertices: {2}".format(
                        len(faces), limit, _preview(faces)),
                    node.path,
                    {"faces": faces},
                ))
        return issues


class CleanManifold(check.BaseCheck):
    """Meshes must have no lamina faces and no non-manifold edges."""

    id = "topology.manifold"
    label = "No lamina or non-manifold geometry"
    category = "topology"
    order = 20
    description = "Uses the lamina/non-manifold indices collected by the adapter."

    def run(self, context):
        issues = []
        for node in context.scene.mesh_nodes():
            mesh = node.mesh
            if mesh.lamina_faces:
                issues.append(check.Issue(
                    "lamina faces: {0}".format(_preview(mesh.lamina_faces)),
                    node.path, {"faces": list(mesh.lamina_faces)}))
            if mesh.non_manifold_edges:
                issues.append(check.Issue(
                    "non-manifold edges: {0}".format(_preview(mesh.non_manifold_edges)),
                    node.path, {"edges": list(mesh.non_manifold_edges)}))
        return issues


def _preview(indices):
    shown = ", ".join(str(i) for i in indices[:MAX_LISTED])
    return shown + (", ..." if len(indices) > MAX_LISTED else "")
