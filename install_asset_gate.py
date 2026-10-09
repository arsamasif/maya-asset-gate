"""Drag this file into the Maya viewport to install asset_gate.

Maya runs a dropped Python file and calls ``onMayaDroppedPythonFile``. The
function finds this repo folder and hands over to ``asset_gate.install.run``,
which writes a module file for the current user, installs PyYAML if needed
and adds a shelf button for the checklist.

"""

import os
import sys


def _repo_root():
    # Maya does not always set __file__ for dropped files, so the path comes
    # from this function's code object instead.
    return os.path.dirname(os.path.abspath(_repo_root.__code__.co_filename))


def onMayaDroppedPythonFile(*args):
    """Entry point Maya calls when the file is dropped into the viewport."""
    root = _repo_root()
    python_dir = os.path.join(root, "python")
    if python_dir not in sys.path:
        sys.path.insert(0, python_dir)
    from asset_gate import install

    try:
        install.run(root)
    finally:
        # Maya imports dropped files as modules named after the file, and a
        # cached module would be reused on the next drop. Forgetting it here
        # makes a re-drop run the current file.
        sys.modules.pop(__name__, None)
