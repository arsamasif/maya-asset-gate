"""Run checks in a stable order and collect their results.

The runner sorts checks by category, then ``order``, then id, runs each
one in isolation (an exception becomes an ``error`` result instead of
aborting the run), optionally applies fixes and re-runs the check to
confirm the fix worked.

"""

import time
import traceback
from dataclasses import dataclass, field

from asset_gate import check as check_mod

PASS = "pass"
WARN = "warn"
FAIL = "fail"
ERRORED = "error"
STATUSES = (PASS, WARN, FAIL, ERRORED)


@dataclass
class CheckResult:
    """Outcome of one check."""

    check_id: str
    label: str
    category: str
    severity: str
    status: str
    issues: list = field(default_factory=list)
    error: str = ""
    fixable: bool = False
    fixed: bool = False
    duration: float = 0.0

    def to_dict(self):
        """Return a JSON-compatible representation.

        Returns:
            dict: Result fields.

        """
        return {
            "id": self.check_id,
            "label": self.label,
            "category": self.category,
            "severity": self.severity,
            "status": self.status,
            "issues": [issue.to_dict() for issue in self.issues],
            "error": self.error,
            "fixable": self.fixable,
            "fixed": self.fixed,
            "duration": round(self.duration, 4),
        }


def sort_checks(checks):
    """Return checks ordered by category, ``order`` and id.

    Args:
        checks (iterable): Check instances.

    Returns:
        list: Sorted checks.

    """
    def key(check):
        return (check_mod.CATEGORIES.index(check.category), check.order, check.id)
    return sorted(checks, key=key)


def run_check(check, context):
    """Run a single check, turning exceptions into an ``error`` result.

    Args:
        check (BaseCheck): Check to run.
        context (Context): Scene, config and editor.

    Returns:
        CheckResult: The outcome.

    """
    start = time.perf_counter()
    result = CheckResult(
        check_id=check.id,
        label=check.label or check.id,
        category=check.category,
        severity=check.severity,
        status=PASS,
        fixable=check.fixable(),
    )
    try:
        issues = list(check.run(context) or [])
    except Exception:
        result.status = ERRORED
        result.error = traceback.format_exc()
    else:
        result.issues = issues
        result.status = status_for(check.severity, issues)
    result.duration = time.perf_counter() - start
    return result


def fix_check(check, context, result):
    """Apply a check's fix and re-run it to confirm.

    Args:
        check (BaseCheck): Check that produced ``result``.
        context (Context): Context with an editor; its scene is refreshed.
        result (CheckResult): Failing result to fix.

    Returns:
        CheckResult: The re-run result, with ``fixed`` set on success. If the
        fix raises, the original issues are kept and ``error`` holds the
        traceback.

    """
    if context.editor is None:
        raise ValueError("Fixing requires a context with an editor")
    try:
        check.fix(context, result.issues)
    except Exception:
        result.status = ERRORED
        result.error = "Fix failed:\n" + traceback.format_exc()
        return result
    finally:
        context.scene = context.editor.refresh()
    rerun = run_check(check, context)
    rerun.fixed = rerun.status == PASS
    return rerun


def run(checks, context, fix=False):
    """Run checks in order and return their results.

    Args:
        checks (iterable): Check instances.
        context (Context): Scene, config and editor.
        fix (bool): Apply available fixes to failing checks.

    Returns:
        list: ``CheckResult`` per check, in run order.

    """
    results = []
    for check in sort_checks(checks):
        result = run_check(check, context)
        if fix and result.fixable and result.status in (WARN, FAIL):
            result = fix_check(check, context, result)
        results.append(result)
    return results


def status_for(severity, issues):
    """Map a check's severity and issues to a result status.

    Args:
        severity (str): Check severity.
        issues (list): Issues reported.

    Returns:
        str: ``pass``, ``warn`` or ``fail``.

    """
    if not issues or severity == check_mod.INFO:
        return PASS
    return FAIL if severity == check_mod.ERROR else WARN
