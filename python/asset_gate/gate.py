"""High-level validate and publish entry points.

These wire the pieces together the way the CLI, the checklist dialog and
a Maya shelf button all want them: discover checks, honour the config,
run with or without fixes, and refuse to publish an asset that fails.

"""

from asset_gate import check
from asset_gate import config as config_mod
from asset_gate import editor as editor_mod
from asset_gate import registry
from asset_gate import report
from asset_gate import runner


class PublishBlocked(RuntimeError):
    """Raised when validation fails and publishing was not forced."""

    def __init__(self, results):
        super().__init__("Validation failed; fix the failing checks or force the publish")
        self.results = results


def load_checks(config=None, plugin_dirs=()):
    """Discover checks and drop the ones the config disables.

    Args:
        config (dict): Loaded config, or None for defaults.
        plugin_dirs (iterable): Extra plugin folders.

    Returns:
        list: Check instances.

    """
    config = config or {}
    folders = list(plugin_dirs) + config_mod.plugin_dirs(config)
    found = registry.discover(plugin_dirs=folders)
    return found.create(disabled=config_mod.disabled(config))


def make_context(scene, config=None, editor=None):
    """Build a check context, defaulting to a pure SceneData editor.

    Args:
        scene (SceneData): Scene to validate.
        config (dict): Loaded config, or None for defaults.
        editor (object): Editor for fixes; a ``SceneEditor`` if None.

    Returns:
        Context: The context.

    """
    return check.Context(
        scene=scene,
        config=config or {},
        editor=editor if editor is not None else editor_mod.SceneEditor(scene),
    )


def validate(context, checks=None, fix=False):
    """Run checks against a context.

    Args:
        context (Context): Scene, config and editor.
        checks (list): Check instances; discovered from the config if None.
        fix (bool): Apply fixes to failing checks.

    Returns:
        list: ``CheckResult`` objects.

    """
    if checks is None:
        checks = load_checks(context.config)
    return runner.run(checks, context, fix=fix)


def publish(context, out_dir, checks=None, force=False):
    """Validate the scene and write the USD asset if it passes.

    Args:
        context (Context): Scene, config and editor.
        out_dir (str): Destination folder for the USD layers.
        checks (list): Check instances; discovered from the config if None.
        force (bool): Publish even when validation fails.

    Returns:
        tuple: ``(results, PublishResult)``.

    Raises:
        PublishBlocked: If validation fails and ``force`` is False.

    """
    results = validate(context, checks)
    if not force and not report.summarize(results)["publishable"]:
        raise PublishBlocked(results)
    # Imported here so validating and fixing work without USD installed.
    from asset_gate import usd_publish

    return results, usd_publish.publish(context.scene, out_dir)
