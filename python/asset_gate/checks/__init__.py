"""Built-in checks shipped with asset_gate.

Each submodule groups the checks for one category. ``BUILTIN_CHECKS`` is
the list the registry loads by default; studios add their own through
entry points or a plugin folder.

"""

from asset_gate.checks import hierarchy
from asset_gate.checks import lod
from asset_gate.checks import materials
from asset_gate.checks import naming
from asset_gate.checks import topology
from asset_gate.checks import transforms
from asset_gate.checks import uvs

BUILTIN_CHECKS = (
    hierarchy.SingleRoot,
    hierarchy.EmptyGroups,
    naming.NamingConvention,
    naming.UniqueNames,
    transforms.FrozenTransforms,
    transforms.NoHistory,
    transforms.PivotPlacement,
    topology.NoNgons,
    topology.CleanManifold,
    uvs.UVSetsPresent,
    uvs.UVRange,
    materials.MaterialAssigned,
    materials.TexturesExist,
    lod.PolyBudget,
    lod.LODConsistency,
)
