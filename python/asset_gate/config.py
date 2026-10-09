"""Load validation settings from a JSON or YAML file.

A config is a mapping keyed by check id, holding that check's options,
plus a few reserved keys: ``disabled`` (check ids to skip) and
``plugin_dirs`` (extra plugin folders, relative to the config file).

Example::

    disabled: [uv.range]
    naming.convention:
      mesh_pattern: "^[a-z]+_GEO$"
    lod.budget:
      budgets: {LOD0: 12000, LOD1: 4000}

"""

import json
import os

RESERVED_KEYS = ("disabled", "plugin_dirs")


def load(path):
    """Read a config file.

    Args:
        path (str): ``.json``, ``.yaml`` or ``.yml`` file.

    Returns:
        dict: The config, with ``plugin_dirs`` made absolute.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the extension is unknown or the content is not a mapping.

    """
    if not os.path.isfile(path):
        raise FileNotFoundError("Missing config file: {0}".format(path))
    extension = os.path.splitext(path)[1].lower()
    with open(path, "r", encoding="utf-8") as handle:
        if extension == ".json":
            data = json.load(handle)
        elif extension in (".yaml", ".yml"):
            import yaml
            data = yaml.safe_load(handle) or {}
        else:
            raise ValueError("Unsupported config format: {0}".format(path))
    if not isinstance(data, dict):
        raise ValueError("Config must be a mapping: {0}".format(path))
    folder = os.path.dirname(os.path.abspath(path))
    data["plugin_dirs"] = [
        os.path.normpath(os.path.join(folder, item)) for item in data.get("plugin_dirs", [])
    ]
    return data


def disabled(config):
    """Return the ids of checks the config turns off.

    Args:
        config (dict): Loaded config.

    Returns:
        list: Check ids.

    """
    return list(config.get("disabled", []))


def plugin_dirs(config):
    """Return the extra plugin folders listed in the config.

    Args:
        config (dict): Loaded config.

    Returns:
        list: Absolute folder paths.

    """
    return list(config.get("plugin_dirs", []))
