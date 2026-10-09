"""Tests for check ordering, exception isolation, fixes and reports.

"""

import json

import pytest

from asset_gate import check
from asset_gate import gate
from asset_gate import report
from asset_gate import runner
from asset_gate.test import scenes


class _Recorder(check.BaseCheck):
    calls = []

    def run(self, context):
        self.calls.append(self.id)
        return []


class LateLod(_Recorder):
    id = "z.lod"
    category = "lod"


class EarlyScene(_Recorder):
    id = "b.scene"
    category = "scene"
    order = 5


class SecondScene(_Recorder):
    id = "a.scene"
    category = "scene"
    order = 50


class Exploding(check.BaseCheck):
    id = "boom"
    category = "naming"

    def run(self, context):
        raise RuntimeError("check crashed")


class CountsToThree(check.BaseCheck):
    """Fails until the scene's version reaches 3; the fix bumps it."""

    id = "version"
    severity = check.WARNING

    def run(self, context):
        version = context.scene.version
        return [] if version >= 3 else [check.Issue("version {0}".format(version))]

    def fix(self, context, issues):
        context.scene.version += 1


class BrokenFix(check.BaseCheck):
    id = "broken.fix"

    def run(self, context):
        return [check.Issue("always")]

    def fix(self, context, issues):
        raise RuntimeError("fix crashed")


@pytest.fixture
def context():
    return gate.make_context(scenes.chair_scene())


def test_checks_run_in_category_then_order_then_id(context):
    _Recorder.calls = []
    results = runner.run([LateLod(), SecondScene(), EarlyScene()], context)
    assert _Recorder.calls == ["b.scene", "a.scene", "z.lod"]
    assert [r.check_id for r in results] == _Recorder.calls


def test_exception_is_isolated(context):
    results = runner.run([Exploding(), LateLod()], context)
    assert results[0].status == runner.ERRORED
    assert "check crashed" in results[0].error
    assert results[1].status == runner.PASS
    assert not report.summarize(results)["publishable"]


def test_fix_reruns_until_clean(context):
    context.scene.version = 2
    result = runner.run([CountsToThree()], context, fix=True)[0]
    assert result.status == runner.PASS and result.fixed
    assert context.scene.version == 3


def test_failed_fix_is_reported_not_raised(context):
    result = runner.run([BrokenFix()], context, fix=True)[0]
    assert result.status == runner.ERRORED
    assert "fix crashed" in result.error
    assert result.issues


def test_no_fix_without_flag(context):
    context.scene.version = 1
    result = runner.run([CountsToThree()], context)[0]
    assert result.status == runner.WARN and not result.fixed
    assert result.fixable and BrokenFix.fixable() and not Exploding.fixable()


def test_fix_requires_editor():
    context = check.Context(scenes.chair_scene())
    with pytest.raises(ValueError):
        runner.fix_check(BrokenFix(), context, runner.run_check(BrokenFix(), context))


def test_status_mapping():
    issue = [check.Issue("x")]
    assert runner.status_for(check.ERROR, issue) == runner.FAIL
    assert runner.status_for(check.WARNING, issue) == runner.WARN
    assert runner.status_for(check.INFO, issue) == runner.PASS
    assert runner.status_for(check.ERROR, []) == runner.PASS


def test_fix_all_on_broken_chair_makes_it_publishable():
    scene = scenes.chair_scene()
    scene.get("|chair|geo").translate = (0, 3, 0)
    scene.get("|chair").pivot = (0, 10, 0)
    scene.get("|chair|geo|LOD0|seat_LOD0_GEO").history = ["polyExtrudeFace"]
    scene.rename("|chair|geo|LOD1|seat_LOD1_GEO", "seat_LOD1")
    context = gate.make_context(scene)
    results = gate.validate(context, fix=True)
    summary = report.summarize(results)
    assert summary["publishable"]
    assert summary["fixed"] == 4


def test_report_json_and_console(context, tmp_path):
    context.scene.version = 1
    results = runner.run([Exploding(), CountsToThree()], context)
    path = str(tmp_path / "report.json")
    report.write_json(results, path, "chair")
    with open(path) as handle:
        data = json.load(handle)
    assert data["asset"] == "chair"
    assert data["summary"]["error"] == 1 and data["summary"]["warn"] == 1
    by_id = {item["id"]: item for item in data["checks"]}
    assert by_id["version"]["issues"][0]["message"] == "version 1"

    text = report.format_console(results, "chair")
    assert "[ERR ] boom" in text
    assert "[WARN] version" in text
    assert "Not publishable." in text


def test_console_truncates_issues(context):
    result = runner.CheckResult("many", "Many", "scene", check.ERROR, runner.FAIL,
                                issues=[check.Issue(str(i)) for i in range(8)])
    assert "... 3 more" in report.format_console([result])
    assert "... 3 more" not in report.format_console([result], verbose=True)
