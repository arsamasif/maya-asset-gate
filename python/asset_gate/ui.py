"""Qt checklist dialog: run checks, show pass/warn/fail, fix, publish.

The widget is a thin view over ``checklist.ChecklistModel``. It works with
PySide6 (Maya 2025+) and PySide2 (Maya 2024). In Maya, call ``show()``
from a shelf button; outside Maya, pass any context to ``ChecklistDialog``.

"""

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:  # Maya 2024 ships PySide2.
    from PySide2 import QtCore, QtGui, QtWidgets

from asset_gate import checklist
from asset_gate import gate

WINDOW_TITLE = "Asset Gate"
OBJECT_NAME = "assetGateChecklist"
COLUMNS = ("Check", "Status", "Issues", "")


class ChecklistDialog(QtWidgets.QDialog):
    """List every check with its status, a Fix button and the issue text.

    Args:
        model (ChecklistModel): Model holding the context and checks.
        parent (QWidget): Parent window.

    """

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.model = model
        self.setObjectName(OBJECT_NAME)
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(640, 520)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(COLUMNS)
        self.tree.setRootIsDecorated(False)
        self.tree.header().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.tree.currentItemChanged.connect(self._show_detail)

        self.detail = QtWidgets.QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.summary = QtWidgets.QLabel()

        validate_button = QtWidgets.QPushButton("Validate")
        validate_button.clicked.connect(self.validate)
        fix_all_button = QtWidgets.QPushButton("Fix All")
        fix_all_button.clicked.connect(self.fix_all)
        self.publish_button = QtWidgets.QPushButton("Publish...")
        self.publish_button.clicked.connect(self.publish)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addWidget(self.summary, 1)
        for button in (validate_button, fix_all_button, self.publish_button):
            buttons.addWidget(button)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        splitter.addWidget(self.tree)
        splitter.addWidget(self.detail)
        splitter.setSizes([360, 140])

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(splitter)
        layout.addLayout(buttons)
        self.refresh()

    def validate(self):
        """Run every check and redraw."""
        self.model.run_all()
        self.refresh()

    def fix(self, check_id):
        """Fix one check and redraw.

        Args:
            check_id (str): Check to fix.

        """
        self.model.fix(check_id)
        self.refresh()

    def fix_all(self):
        """Fix every fixable failing check and redraw."""
        self.model.fix_all()
        self.refresh()

    def publish(self):
        """Ask for an output folder and publish the asset there."""
        out_dir = QtWidgets.QFileDialog.getExistingDirectory(self, "Publish to folder")
        if not out_dir:
            return
        try:
            written = self.model.publish(out_dir)
        except gate.PublishBlocked:
            QtWidgets.QMessageBox.warning(self, WINDOW_TITLE, "Validation failed; not published.")
            self.validate()
            return
        QtWidgets.QMessageBox.information(self, WINDOW_TITLE, f"Published {written.asset}")

    def refresh(self):
        """Rebuild the rows from the model."""
        selected = self.tree.currentItem()
        selected_id = selected.data(0, QtCore.Qt.UserRole) if selected else None
        self.tree.clear()
        for row in self.model.rows():
            item = QtWidgets.QTreeWidgetItem([row.label, row.status.upper(), str(row.issue_count)])
            item.setData(0, QtCore.Qt.UserRole, row.check_id)
            item.setForeground(1, QtGui.QBrush(QtGui.QColor(row.color)))
            item.setToolTip(0, row.check_id)
            self.tree.addTopLevelItem(item)
            if row.can_fix:
                button = QtWidgets.QPushButton("Fix")
                button.clicked.connect(lambda _=False, cid=row.check_id: self.fix(cid))
                self.tree.setItemWidget(item, 3, button)
            if row.check_id == selected_id:
                self.tree.setCurrentItem(item)
        self.summary.setText(self.model.summary_text())
        self.publish_button.setEnabled(self.model.can_publish())

    def _show_detail(self, current, _previous=None):
        check_id = current.data(0, QtCore.Qt.UserRole) if current else None
        self.detail.setPlainText(self.model.detail(check_id) if check_id else "")


def show(root=None, config=None):
    """Open the dialog in Maya for the selected (or only) asset root.

    Args:
        root (str): Root transform; uses the selection if None.
        config (dict): Loaded config, or None for defaults.

    Returns:
        ChecklistDialog: The dialog, kept alive by its Maya parent.

    """
    from asset_gate import maya_adapter

    parent = _maya_main_window()
    try:
        context = maya_adapter.make_context(root, config)
    except ValueError as error:
        QtWidgets.QMessageBox.warning(parent, WINDOW_TITLE, str(error))
        return None
    if parent is not None:
        for old in parent.findChildren(QtWidgets.QDialog, OBJECT_NAME):
            old.close()
            old.deleteLater()
    dialog = ChecklistDialog(checklist.ChecklistModel(context), parent)
    dialog.setWindowTitle("{0}: {1}".format(WINDOW_TITLE, context.scene.name))
    dialog.show()
    dialog.validate()
    return dialog


def _maya_main_window():
    from maya import OpenMayaUI

    try:
        from shiboken6 import wrapInstance
    except ImportError:
        from shiboken2 import wrapInstance
    pointer = OpenMayaUI.MQtUtil.mainWindow()
    return wrapInstance(int(pointer), QtWidgets.QWidget) if pointer else None
