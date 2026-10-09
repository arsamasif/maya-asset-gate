"""Tests for asset_gate.install that do not need Maya."""

import os
import sys
import types

import pytest

from asset_gate import __version__
from asset_gate import install

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def test_module_text_sets_python_plugin_and_script_paths():
    root = os.path.join(os.path.abspath(os.sep), "tools", "maya-asset-gate")
    lines = install.module_text(root).splitlines()
    assert lines[0] == "+ asset_gate {0} {1}".format(__version__, root.replace("\\", "/"))
    assert lines[1:] == [
        "PYTHONPATH +:= python",
        "PYTHONPATH +:= deps",
    ]


def test_write_module_file(tmp_path):
    modules = str(tmp_path / "modules")
    path = install.write_module_file(REPO_ROOT, modules)
    with open(path, encoding="utf-8") as handle:
        assert handle.read() == install.module_text(REPO_ROOT)
    with pytest.raises(FileNotFoundError, match="Missing asset_gate package"):
        install.write_module_file(str(tmp_path), modules)


def test_add_to_session_adds_paths_once(monkeypatch):
    python_dir = os.path.normpath(os.path.join(REPO_ROOT, "python"))
    monkeypatch.setattr(sys, "path", [p for p in sys.path if os.path.normpath(p) != python_dir])
    install.add_to_session(REPO_ROOT)
    install.add_to_session(REPO_ROOT)
    assert [os.path.normpath(p) for p in sys.path].count(python_dir) == 1


def test_ensure_yaml_installs_into_deps(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "yaml", None)
    monkeypatch.setattr(sys, "path", list(sys.path))
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    assert install.ensure_yaml(str(tmp_path), runner=runner, python="mayapy") == "installed"
    deps = os.path.join(str(tmp_path), "deps")
    assert calls == [["mayapy", "-m", "pip", "install", "--target", deps, "PyYAML"]]


def test_ensure_yaml_reports_pip_failure(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "yaml", None)

    def runner(command, **kwargs):
        return types.SimpleNamespace(returncode=1, stdout="", stderr="no network")

    assert install.ensure_yaml(str(tmp_path), runner=runner, python="mayapy") == (
        "PyYAML install failed: no network"
    )
