"""Smoke test for the Qt dialog; skipped when PySide is not installed.

Runs offscreen and checks that rows and Fix buttons follow the model.

"""

import importlib.util
import os

import pytest

if not any(importlib.util.find_spec(name) for name in ("PySide6", "PySide2")):
    pytest.skip("PySide is not installed", allow_module_level=True)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from asset_gate import checklist  # noqa: E402
from asset_gate import gate  # noqa: E402
from asset_gate import ui  # noqa: E402
from asset_gate.test import scenes  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return ui.QtWidgets.QApplication.instance() or ui.QtWidgets.QApplication([])


def test_dialog_rows_and_fix(app):
    scene = scenes.chair_scene(2)
    scene.get("|chair|geo").translate = (0.0, 1.0, 0.0)
    dialog = ui.ChecklistDialog(checklist.ChecklistModel(gate.make_context(scene)))
    dialog.validate()
    assert dialog.tree.topLevelItemCount() == 15
    assert not dialog.publish_button.isEnabled()
    dialog.fix_all()
    assert dialog.publish_button.isEnabled()
