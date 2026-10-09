"""Qt-free model behind the checklist dialog.

The dialog only draws rows and forwards button clicks; everything it shows
(status, issue text, whether Fix is enabled, whether Publish is allowed)
comes from ``ChecklistModel``, so that logic is unit tested without Qt.

"""

from dataclasses import dataclass

from asset_gate import gate
from asset_gate import report
from asset_gate import runner

STATUS_COLORS = {
    runner.PASS: "#3d9a4b",
    runner.WARN: "#d8a227",
    runner.FAIL: "#c8433a",
    runner.ERRORED: "#8a4fc0",
}
PENDING = "pending"


@dataclass
class Row:
    """What the dialog shows for one check."""

    check_id: str
    label: str
    category: str
    status: str
    issue_count: int
    can_fix: bool
    fixed: bool
    detail: str

    @property
    def color(self):
        """str: Hex color for the status badge."""
        return STATUS_COLORS.get(self.status, "#808080")


class ChecklistModel:
    """Run checks, keep the latest result per check and expose rows.

    Args:
        context (Context): Scene, config and editor (Maya or pure).
        checks (list): Check instances, discovered if None.

    """

    def __init__(self, context, checks=None):
        self.context = context
        self.checks = runner.sort_checks(
            checks if checks is not None else gate.load_checks(context.config))
        self._results = {}

    def run_all(self):
        """Run every check.

        Returns:
            list: Updated rows.

        """
        for check in self.checks:
            self._results[check.id] = runner.run_check(check, self.context)
        return self.rows()

    def fix(self, check_id):
        """Fix one check and refresh every result, since fixes can interact.

        Args:
            check_id (str): Check to fix.

        Returns:
            Row: The fixed check's row.

        Raises:
            ValueError: If the check has no fix or has not failed.

        """
        check = self._check(check_id)
        result = self._results.get(check_id)
        if result is None or not self._can_fix(result):
            raise ValueError("Nothing to fix for check: {0}".format(check_id))
        fixed = runner.fix_check(check, self.context, result)
        self.run_all()
        if fixed.status == runner.ERRORED:
            self._results[check_id] = fixed
        else:
            self._results[check_id].fixed = fixed.fixed
        return self.row(check_id)

    def fix_all(self):
        """Fix every fixable failing check, then re-run everything.

        Returns:
            list: Updated rows.

        """
        for check in self.checks:
            result = self._results.get(check.id)
            if result is not None and self._can_fix(result):
                self._results[check.id] = runner.fix_check(check, self.context, result)
        fixed = {check_id for check_id, result in self._results.items() if result.fixed}
        self.run_all()
        for check_id in fixed:
            self._results[check_id].fixed = True
        return self.rows()

    def rows(self):
        """Return one row per check in run order.

        Returns:
            list: ``Row`` objects; checks not yet run are ``pending``.

        """
        return [self.row(check.id) for check in self.checks]

    def row(self, check_id):
        """Return the row for one check.

        Args:
            check_id (str): Check id.

        Returns:
            Row: The row.

        """
        check = self._check(check_id)
        result = self._results.get(check_id)
        if result is None:
            return Row(check.id, check.label, check.category, PENDING, 0, False, False, "")
        return Row(
            check_id=check.id,
            label=result.label,
            category=result.category,
            status=result.status,
            issue_count=len(result.issues),
            can_fix=self._can_fix(result),
            fixed=result.fixed,
            detail=self.detail(check_id),
        )

    def detail(self, check_id):
        """Return the issue text for one check, one line per issue.

        Args:
            check_id (str): Check id.

        Returns:
            str: Issue lines, the error traceback, or "" when passing.

        """
        result = self._results.get(check_id)
        if result is None:
            return ""
        if result.error:
            return result.error.strip()
        return "\n".join(
            f"{issue.node}: {issue.message}" if issue.node else issue.message
            for issue in result.issues
        )

    def summary_text(self):
        """Return a one-line summary for the dialog footer.

        Returns:
            str: Counts per status.

        """
        if not self._results:
            return "Not validated yet."
        summary = report.summarize(list(self._results.values()))
        return "{0} passed, {1} warnings, {2} failed, {3} errors".format(
            summary[runner.PASS], summary[runner.WARN], summary[runner.FAIL],
            summary[runner.ERRORED])

    def can_publish(self):
        """Return True once every check has run and nothing failed.

        Returns:
            bool: Whether Publish should be enabled.

        """
        if len(self._results) != len(self.checks):
            return False
        return report.summarize(list(self._results.values()))["publishable"]

    def publish(self, out_dir):
        """Publish the current scene to USD.

        Args:
            out_dir (str): Destination folder.

        Returns:
            PublishResult: Written layer paths.

        Raises:
            PublishBlocked: If the asset does not pass validation.

        """
        _, written = gate.publish(self.context, out_dir, self.checks)
        return written

    def _check(self, check_id):
        for check in self.checks:
            if check.id == check_id:
                return check
        raise KeyError("Unknown check: {0}".format(check_id))

    @staticmethod
    def _can_fix(result):
        return result.fixable and result.status in (runner.WARN, runner.FAIL)
