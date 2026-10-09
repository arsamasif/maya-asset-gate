"""Install asset_gate for one Maya user without touching environment setup.

Writes a Maya module file (``asset_gate.mod``) into the user's modules
folder, so Maya finds the Python package at every launch, and puts it on
``sys.path`` for the running session too. PyYAML (needed for YAML configs,
missing from stock Maya) is pip-installed into the repo's ``deps`` folder
with Maya's own Python. Finally an "AssetGate" button that opens the
checklist on the selected asset goes on the current shelf. The USD publish
uses the ``pxr`` modules that come with MayaUSD.
``install_asset_gate.py`` at the repo root calls ``run``.

"""

import importlib
import os
import subprocess
import sys

from asset_gate import __version__

MODULE_NAME = "asset_gate"
MOD_FILE = MODULE_NAME + ".mod"
DEPS_DIR = "deps"
SHELF_LABEL = "AssetGate"
SHELF_TAG = "assetGateChecklist"
SHELF_COMMAND = "from asset_gate import ui\nui.show()"
SHELF_ICON = "pythonFamily.png"


def module_text(root):
    """Return the contents of the module file for a repo folder.

    Args:
        root (str): Folder that holds ``python/asset_gate``.

    Returns:
        str: Module file text with forward slashes.

    """
    path = os.path.abspath(root).replace("\\", "/")
    lines = [
        "+ {0} {1} {2}".format(MODULE_NAME, __version__, path),
        "PYTHONPATH +:= python",
        "PYTHONPATH +:= {0}".format(DEPS_DIR),
    ]
    return "\n".join(lines) + "\n"


def write_module_file(root, modules_dir):
    """Write (or overwrite) the module file.

    Args:
        root (str): Folder that holds ``python/asset_gate``.
        modules_dir (str): The user's Maya modules folder.

    Returns:
        str: Path of the written file.

    Raises:
        FileNotFoundError: If ``root`` does not contain the package.

    """
    package = os.path.join(root, "python", MODULE_NAME)
    if not os.path.isdir(package):
        raise FileNotFoundError("Missing asset_gate package: {0}".format(package))
    if not os.path.isdir(modules_dir):
        os.makedirs(modules_dir)
    path = os.path.join(modules_dir, MOD_FILE)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(module_text(root))
    return path


def add_to_session(root):
    """Put the package and its dependencies on ``sys.path`` now.

    Args:
        root (str): Folder that holds ``python/asset_gate``.

    Returns:
        list: The folders that are now on ``sys.path``.

    """
    root = os.path.abspath(root)
    folders = [os.path.normpath(os.path.join(root, name)) for name in ("python", DEPS_DIR)]
    current = [os.path.normpath(entry) for entry in sys.path]
    for folder in folders:
        if folder not in current:
            sys.path.append(folder)

    return folders


def ensure_yaml(root, runner=subprocess.run, python=None):
    """Make PyYAML importable, installing it into ``deps`` if needed.

    Args:
        root (str): Repo folder; PyYAML goes into ``<root>/deps``.
        runner (callable): ``subprocess.run`` or a stand-in for tests.
        python (str): Interpreter to run pip with; defaults to ``mayapy``.

    Returns:
        str: ``"present"``, ``"installed"`` or an error message.

    """
    try:
        import yaml  # noqa: F401

        return "present"
    except ImportError:
        pass
    target = os.path.join(os.path.abspath(root), DEPS_DIR)
    command = [python or mayapy_path(), "-m", "pip", "install", "--target", target, "PyYAML"]
    result = runner(command, capture_output=True, text=True)
    if result.returncode != 0:
        return "PyYAML install failed: {0}".format((result.stderr or result.stdout).strip()[-300:])
    if target not in sys.path:
        sys.path.append(target)
    importlib.invalidate_caches()
    return "installed"


def mayapy_path():
    """Return Maya's standalone interpreter next to the running executable.

    Returns:
        str: Path to ``mayapy`` (``mayapy.exe`` on Windows).

    """
    name = "mayapy.exe" if os.name == "nt" else "mayapy"
    return os.path.join(os.path.dirname(sys.executable), name)


def user_modules_dir():
    """Return the current user's Maya modules folder.

    Returns:
        str: ``<user app dir>/modules``.

    """
    from maya import cmds

    return os.path.join(cmds.internalVar(userAppDir=True), "modules")


def add_shelf_button():
    """Add an "AssetGate" button that opens the checklist to the current shelf, once.

    Returns:
        str: The button name, or None when Maya has no shelves (batch mode).

    """
    from maya import cmds
    from maya import mel

    # In batch mode the shelf variable is not declared; checking first avoids
    # a MEL error in the log.
    if mel.eval('whatIs "$gShelfTopLevel"') == "Unknown":
        return None
    top_level = mel.eval("$assetGateShelfTop = $gShelfTopLevel")
    if not top_level or not cmds.tabLayout(top_level, exists=True):
        return None
    shelf = cmds.tabLayout(top_level, query=True, selectTab=True)
    for button in cmds.shelfLayout(shelf, query=True, childArray=True) or []:
        if cmds.shelfButton(button, exists=True) and (
            cmds.shelfButton(button, query=True, docTag=True) == SHELF_TAG
        ):
            return button
    return cmds.shelfButton(
        parent=shelf,
        label=SHELF_LABEL,
        annotation="Validate the selected asset and publish it to USD",
        docTag=SHELF_TAG,
        image=SHELF_ICON,
        imageOverlayLabel="Gate",
        sourceType="python",
        command=SHELF_COMMAND,
    )


def run(root, modules_dir=None, runner=subprocess.run):
    """Install for the current user and print what was done.

    Args:
        root (str): Folder that holds ``python/asset_gate``.
        modules_dir (str): Modules folder; defaults to the user's.
        runner (callable): Used to run pip; replaced in tests.

    Returns:
        dict: ``module_file``, ``yaml`` and ``shelf_button``.

    """
    module_file = write_module_file(root, modules_dir or user_modules_dir())
    add_to_session(root)
    yaml_status = ensure_yaml(root, runner=runner)
    button = add_shelf_button()
    print("=" * 60)
    print(f"asset_gate {__version__} installed")
    print(f"  module file : {module_file}")
    print(f"  PyYAML      : {yaml_status}")
    print(f"  shelf button: {button or 'none (no shelves in this session)'}")
    print("=" * 60)
    return {"module_file": module_file, "yaml": yaml_status, "shelf_button": button}
