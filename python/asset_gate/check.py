"""Base class and result types for asset checks.

A check is a small class with an id, a label, a category and a severity.
``run`` inspects ``context.scene`` and returns a list of ``Issue`` objects
(an empty list means the check passed). Checks that know how to repair
what they found implement ``fix``, which edits the scene through
``context.editor`` so the same code works on JSON data and in Maya.

"""

from dataclasses import dataclass, field

ERROR = "error"
WARNING = "warning"
INFO = "info"
SEVERITIES = (ERROR, WARNING, INFO)

CATEGORIES = ("scene", "naming", "transform", "topology", "uv", "material", "lod")


@dataclass
class Issue:
    """One problem found by a check, usually tied to a node."""

    message: str
    node: str = ""
    data: dict = field(default_factory=dict)

    def to_dict(self):
        """Return a JSON-compatible representation.

        Returns:
            dict: Issue fields.

        """
        return {"message": self.message, "node": self.node, "data": dict(self.data)}


@dataclass
class Context:
    """Everything a check needs: the scene, configuration and an editor."""

    scene: object
    config: dict = field(default_factory=dict)
    editor: object = None


class BaseCheck:
    """Base class for all checks.

    Subclasses set the class attributes and implement ``run``. Per-check
    options come from ``defaults`` merged with ``config[<check id>]``.

    """

    id = ""
    label = ""
    category = "scene"
    severity = ERROR
    order = 100
    description = ""
    defaults = {}

    def run(self, context):
        """Inspect the scene and report problems.

        Args:
            context (Context): Scene, config and editor.

        Returns:
            list: ``Issue`` objects; empty when the check passes.

        """
        raise NotImplementedError

    def fix(self, context, issues):
        """Repair the given issues through ``context.editor``.

        Args:
            context (Context): Scene, config and editor.
            issues (list): Issues returned by ``run``.

        """
        raise NotImplementedError

    @classmethod
    def fixable(cls):
        """Return True if the subclass implements ``fix``.

        Returns:
            bool: Whether a fix is available.

        """
        return cls.fix is not BaseCheck.fix

    def options(self, context):
        """Return this check's options merged over its defaults.

        Args:
            context (Context): Context holding the config.

        Returns:
            dict: Effective options.

        """
        merged = dict(self.defaults)
        merged.update(context.config.get(self.id, {}))
        return merged


def validate_check_class(cls):
    """Make sure a check class declares the attributes the runner relies on.

    Args:
        cls (type): Candidate check class.

    Raises:
        TypeError: If the class is not a usable ``BaseCheck`` subclass.

    """
    if not (isinstance(cls, type) and issubclass(cls, BaseCheck)) or cls is BaseCheck:
        raise TypeError("Not a check class: {0!r}".format(cls))
    if not cls.id:
        raise TypeError("Check class has no id: {0}".format(cls.__name__))
    if cls.severity not in SEVERITIES:
        raise TypeError("Check {0} has invalid severity {1!r}".format(cls.id, cls.severity))
    if cls.category not in CATEGORIES:
        raise TypeError("Check {0} has invalid category {1!r}".format(cls.id, cls.category))
