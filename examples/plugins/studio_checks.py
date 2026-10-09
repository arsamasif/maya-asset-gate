"""Example plugin: a studio-specific check loaded from a plugin folder.

Drop files like this into a folder listed in ``plugin_dirs`` or in the
``ASSET_GATE_PLUGIN_PATH`` environment variable.

"""

from asset_gate import check


class AssetNameLength(check.BaseCheck):
    """Asset names must be short enough for the render farm's file paths."""

    id = "studio.name_length"
    label = "Asset name length"
    category = "naming"
    severity = check.WARNING
    order = 90
    description = "Asset name is at most max_length characters."
    defaults = {"max_length": 24}

    def run(self, context):
        limit = self.options(context)["max_length"]
        name = context.scene.name
        if len(name) > limit:
            return [check.Issue("asset name has {0} characters, limit is {1}".format(
                len(name), limit))]
        return []
