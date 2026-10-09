"""Summaries of a validation run as JSON and as console text.

The JSON report is what pipelines archive next to a publish; the console
form is what an artist or CI log shows. Both share ``summarize``, which
also decides whether the asset is allowed to publish.

"""

import json

from asset_gate import runner

BANNER_WIDTH = 64
STATUS_TAGS = {
    runner.PASS: "PASS",
    runner.WARN: "WARN",
    runner.FAIL: "FAIL",
    runner.ERRORED: "ERR ",
}
MAX_ISSUES_SHOWN = 5


def summarize(results):
    """Count results per status and decide whether the asset may publish.

    Args:
        results (list): ``CheckResult`` objects.

    Returns:
        dict: Counts per status, ``fixed`` count and ``publishable`` flag.

    """
    counts = {status: 0 for status in runner.STATUSES}
    for result in results:
        counts[result.status] += 1
    counts["fixed"] = sum(1 for result in results if result.fixed)
    counts["publishable"] = counts[runner.FAIL] == 0 and counts[runner.ERRORED] == 0
    return counts


def to_dict(results, scene_name=""):
    """Build the JSON report structure.

    Args:
        results (list): ``CheckResult`` objects.
        scene_name (str): Asset name for the header.

    Returns:
        dict: Report with ``asset``, ``summary`` and ``checks``.

    """
    return {
        "asset": scene_name,
        "summary": summarize(results),
        "checks": [result.to_dict() for result in results],
    }


def write_json(results, path, scene_name=""):
    """Write the JSON report to ``path``.

    Args:
        results (list): ``CheckResult`` objects.
        path (str): Output file.
        scene_name (str): Asset name for the header.

    """
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(to_dict(results, scene_name), handle, indent=2)
        handle.write("\n")


def format_console(results, scene_name="", verbose=False):
    """Render results as readable console text.

    Args:
        results (list): ``CheckResult`` objects.
        scene_name (str): Asset name for the banner.
        verbose (bool): Show every issue instead of the first few.

    Returns:
        str: Multi-line report.

    """
    lines = [banner(f"asset-gate: {scene_name}" if scene_name else "asset-gate")]
    for result in results:
        suffix = " (fixed)" if result.fixed else ""
        lines.append(f"[{STATUS_TAGS[result.status]}] {result.label}{suffix}")
        shown = result.issues if verbose else result.issues[:MAX_ISSUES_SHOWN]
        for issue in shown:
            where = f"{issue.node}: " if issue.node else ""
            lines.append(f"        {where}{issue.message}")
        hidden = len(result.issues) - len(shown)
        if hidden:
            lines.append(f"        ... {hidden} more")
        if result.error:
            lines.append("        " + result.error.strip().splitlines()[-1])
    summary = summarize(results)
    lines.append(banner("summary"))
    lines.append(
        "{0} passed, {1} warnings, {2} failed, {3} errors, {4} fixed".format(
            summary[runner.PASS], summary[runner.WARN], summary[runner.FAIL],
            summary[runner.ERRORED], summary["fixed"]))
    lines.append("Ready to publish." if summary["publishable"] else "Not publishable.")
    return "\n".join(lines)


def banner(title):
    """Return a fixed-width section banner line.

    Args:
        title (str): Section title.

    Returns:
        str: Banner text.

    """
    return f"== {title} ".ljust(BANNER_WIDTH, "=")
