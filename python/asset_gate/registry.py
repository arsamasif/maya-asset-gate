"""Find and register check classes.

Checks come from three places, in this order:

1. the built-in checks shipped in ``asset_gate.checks``,
2. installed packages exposing the ``asset_gate.checks`` entry point group
   (each entry point loads a check class or a module of check classes),
3. plugin folders: every ``*.py`` file in a folder listed by the caller or
   in the ``ASSET_GATE_PLUGIN_PATH`` environment variable.

"""

import importlib.metadata
import importlib.util
import inspect
import os

from asset_gate import check as check_mod

ENTRY_POINT_GROUP = "asset_gate.checks"
PLUGIN_PATH_ENV = "ASSET_GATE_PLUGIN_PATH"


class Registry:
    """A set of check classes keyed by check id."""

    def __init__(self):
        self._checks = {}

    def register(self, cls):
        """Register a check class. Usable as a class decorator.

        Args:
            cls (type): ``BaseCheck`` subclass.

        Returns:
            type: The same class.

        Raises:
            TypeError: If the class is not a valid check.
            ValueError: If another class already uses the id.

        """
        check_mod.validate_check_class(cls)
        existing = self._checks.get(cls.id)
        if existing is not None and existing is not cls:
            raise ValueError("Check id {0!r} already registered by {1}".format(
                cls.id, existing.__name__))
        self._checks[cls.id] = cls
        return cls

    def register_module(self, module):
        """Register every check class defined in a module.

        Args:
            module (module): Module to scan.

        Returns:
            list: Classes registered.

        """
        found = []
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if obj.__module__ != module.__name__:
                continue
            if issubclass(obj, check_mod.BaseCheck) and obj.id:
                found.append(self.register(obj))
        return found

    def get(self, check_id):
        """Return the class registered under ``check_id``.

        Args:
            check_id (str): Check id.

        Returns:
            type: Check class.

        Raises:
            KeyError: If no check has that id.

        """
        try:
            return self._checks[check_id]
        except KeyError:
            raise KeyError("Unknown check: {0}".format(check_id)) from None

    def ids(self):
        """Return registered ids, sorted.

        Returns:
            list: Check ids.

        """
        return sorted(self._checks)

    def create(self, disabled=()):
        """Instantiate every registered check except the disabled ones.

        Args:
            disabled (iterable): Ids to skip.

        Returns:
            list: Check instances.

        """
        skip = set(disabled)
        return [cls() for check_id, cls in sorted(self._checks.items()) if check_id not in skip]

    def __len__(self):
        return len(self._checks)

    def __contains__(self, check_id):
        return check_id in self._checks


def discover(plugin_dirs=(), use_entry_points=True, builtins=True):
    """Build a registry from built-ins, entry points and plugin folders.

    Args:
        plugin_dirs (iterable): Extra folders with ``*.py`` check plugins.
        use_entry_points (bool): Load the ``asset_gate.checks`` entry points.
        builtins (bool): Include the checks shipped with the package.

    Returns:
        Registry: The populated registry.

    """
    registry = Registry()
    if builtins:
        from asset_gate import checks
        for cls in checks.BUILTIN_CHECKS:
            registry.register(cls)
    if use_entry_points:
        for entry_point in importlib.metadata.entry_points(group=ENTRY_POINT_GROUP):
            _register_object(registry, entry_point.load())
    folders = list(plugin_dirs)
    folders.extend(p for p in os.environ.get(PLUGIN_PATH_ENV, "").split(os.pathsep) if p)
    for folder in folders:
        load_plugin_folder(registry, folder)
    return registry


def load_plugin_folder(registry, folder):
    """Import every ``*.py`` file in ``folder`` and register its checks.

    Args:
        registry (Registry): Registry to add to.
        folder (str): Plugin folder.

    Returns:
        list: Classes registered.

    Raises:
        FileNotFoundError: If the folder does not exist.

    """
    if not os.path.isdir(folder):
        raise FileNotFoundError("Missing plugin folder: {0}".format(folder))
    found = []
    for filename in sorted(os.listdir(folder)):
        if not filename.endswith(".py") or filename.startswith("_"):
            continue
        module = _import_file(os.path.join(folder, filename))
        found.extend(registry.register_module(module))
    return found


def _register_object(registry, obj):
    if inspect.ismodule(obj):
        registry.register_module(obj)
    else:
        registry.register(obj)


def _import_file(path):
    name = "asset_gate_plugin_{0}".format(os.path.splitext(os.path.basename(path))[0])
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
