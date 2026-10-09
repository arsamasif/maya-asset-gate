"""Tests for the asset-gate command line.

"""

import json
import os

import pytest

from asset_gate import cli
from asset_gate import scene as scene_mod
from asset_gate.test import scenes


@pytest.fixture
def clean_json(tmp_path):
    path = str(tmp_path / "chair.json")
    scene_mod.save(scenes.chair_scene(2), path)
    return path


@pytest.fixture
def broken_json(tmp_path):
    scene = scenes.chair_scene(2)
    scene.get("|chair|geo").scale = (2.0, 2.0, 2.0)
    scene.get("|chair|geo|LOD0|seat_LOD0_GEO").history = ["polyCube"]
    path = str(tmp_path / "broken.json")
    scene_mod.save(scene, path)
    return path


def test_validate_clean_scene(clean_json, tmp_path, capsys):
    report_path = str(tmp_path / "report.json")
    assert cli.main(["validate", clean_json, "--report", report_path]) == cli.EXIT_OK
    assert "Ready to publish." in capsys.readouterr().out
    with open(report_path) as handle:
        assert json.load(handle)["summary"]["publishable"] is True


def test_validate_broken_scene_fails(broken_json, capsys):
    assert cli.main(["validate", broken_json]) == cli.EXIT_FAILED
    out = capsys.readouterr().out
    assert "[FAIL] Frozen transforms" in out
    assert "[FAIL] No construction history" in out


def test_validate_fix_writes_fixed_scene(broken_json, tmp_path):
    fixed_path = str(tmp_path / "fixed.json")
    assert cli.main(["validate", broken_json, "--fix", "--write-fixed", fixed_path]) == 0
    assert cli.main(["validate", fixed_path]) == cli.EXIT_OK


def test_publish_writes_layers(clean_json, tmp_path):
    out_dir = str(tmp_path / "publish")
    assert cli.main(["publish", clean_json, "--out", out_dir]) == cli.EXIT_OK
    assert sorted(os.listdir(out_dir)) == ["chair.usda", "geo.usda", "mtl.usda", "payload.usda"]


def test_publish_is_blocked_unless_forced(broken_json, tmp_path, capsys):
    out_dir = str(tmp_path / "publish")
    assert cli.main(["publish", broken_json, "--out", out_dir]) == cli.EXIT_FAILED
    assert "Publish blocked" in capsys.readouterr().out
    assert not os.path.exists(out_dir)
    assert cli.main(["publish", broken_json, "--out", out_dir, "--force"]) == cli.EXIT_OK
    assert os.path.isfile(os.path.join(out_dir, "chair.usda"))


def test_config_and_plugins(clean_json, tmp_path, capsys):
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    (plugins / "studio.py").write_text(
        "from asset_gate import check\n"
        "class AlwaysWarn(check.BaseCheck):\n"
        "    id = 'studio.warn'\n"
        "    label = 'Studio warning'\n"
        "    severity = check.WARNING\n"
        "    def run(self, context):\n"
        "        return [check.Issue('heads up')]\n")
    config = tmp_path / "config.yaml"
    config.write_text("disabled: [uv.range]\nplugin_dirs: [plugins]\n"
                      "lod.budget:\n  budgets: {LOD0: 10}\n")
    assert cli.main(["validate", clean_json, "--config", str(config)]) == cli.EXIT_FAILED
    out = capsys.readouterr().out
    assert "[WARN] Studio warning" in out
    assert "UVs inside 0-1" not in out
    assert "LOD0 has 144 triangles, budget is 10" in out


def test_bad_input_returns_usage_code(tmp_path, capsys):
    assert cli.main(["validate", str(tmp_path / "missing.json")]) == cli.EXIT_USAGE
    assert "Missing scene file" in capsys.readouterr().err
    bad_config = tmp_path / "config.txt"
    bad_config.write_text("x")
    assert cli.main(["validate", "x.json", "--config", str(bad_config)]) == cli.EXIT_USAGE


def test_list_checks(capsys):
    assert cli.main(["checks"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "transform.frozen" in out and "fix" in out
