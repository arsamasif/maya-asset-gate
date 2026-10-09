"""Shared pytest setup for the asset_gate tests.

Under ``mayapy`` the Maya tests call ``maya.standalone.initialize`` at import
time, and Maya then creates a ``QCoreApplication``. Qt widgets cannot be built
on top of that, so the UI test would crash the interpreter. Creating the
``QApplication`` here, before any test module is collected, makes Maya reuse
it and lets both kinds of test run in one session.

"""

import importlib.util
import os

if any(importlib.util.find_spec(name) for name in ("PySide6", "PySide2")):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from asset_gate import ui

    QT_APP = ui.QtWidgets.QApplication.instance() or ui.QtWidgets.QApplication([])
