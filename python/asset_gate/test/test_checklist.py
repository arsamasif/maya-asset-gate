"""Tests for the Qt-free checklist model behind the dialog.

"""

import pytest

from asset_gate import checklist
from asset_gate import gate
from asset_gate import runner
from asset_gate.test import scenes


@pytest.fixture
def model():
    scene = scenes.chair_scene(2)
    scene.get("|chair|geo").rotate = (0.0, 10.0, 0.0)
    scene.get("|chair|geo|LOD0|legs_LOD0_GEO").mesh.face_counts[0] = 6
    return checklist.ChecklistModel(gate.make_context(scene))


def _row(model, check_id):
    return model.row(check_id)


def test_rows_start_pending(model):
    rows = model.rows()
    assert len(rows) == 15
    assert {row.status for row in rows} == {checklist.PENDING}
    assert model.summary_text() == "Not validated yet."
    assert not model.can_publish()


def test_run_all_reports_status_and_fixability(model):
    model.run_all()
    frozen = _row(model, "transform.frozen")
    assert frozen.status == runner.FAIL and frozen.can_fix
    assert frozen.color == checklist.STATUS_COLORS[runner.FAIL]
    assert "|chair|geo: non-identity rotate" in frozen.detail
    ngons = _row(model, "topology.ngons")
    assert ngons.status == runner.FAIL and not ngons.can_fix
    assert "2 failed" in model.summary_text()


def test_fix_one_check(model):
    model.run_all()
    row = model.fix("transform.frozen")
    assert row.status == runner.PASS and row.fixed and not row.can_fix
    with pytest.raises(ValueError):
        model.fix("transform.frozen")
    with pytest.raises(KeyError):
        model.fix("nope")


def test_fix_all_then_publish(model, tmp_path):
    model.run_all()
    model.fix_all()
    assert not model.can_publish()  # n-gons have no automatic fix
    with pytest.raises(gate.PublishBlocked):
        model.publish(str(tmp_path))

    model.context.scene.get("|chair|geo|LOD0|legs_LOD0_GEO").mesh.face_counts[0] = 4
    model.run_all()
    assert model.can_publish()
    written = model.publish(str(tmp_path))
    assert written.asset.endswith("chair.usda")
