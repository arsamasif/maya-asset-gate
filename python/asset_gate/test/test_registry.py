"""Tests for check discovery: built-ins, plugin folders and entry points.

"""

import importlib.metadata
import textwrap

import pytest

from asset_gate import check
from asset_gate import checks
from asset_gate import gate
from asset_gate import registry

PLUGIN = textwrap.dedent('''
    from asset_gate import check

    class StudioPrefix(check.BaseCheck):
        id = "studio.prefix"
        label = "Studio prefix"
        category = "naming"

        def run(self, context):
            return []
''')


class EntryPointCheck(check.BaseCheck):
    id = "ep.check"

    def run(self, context):
        return []


class _FakeEntryPoint:
    def __init__(self, obj):
        self.obj = obj

    def load(self):
        return self.obj


def test_builtins_are_registered():
    found = registry.discover(use_entry_points=False)
    assert len(found) == len(checks.BUILTIN_CHECKS) == 15
    assert "naming.convention" in found


def test_plugin_folder_and_env_var(tmp_path, monkeypatch):
    (tmp_path / "studio_checks.py").write_text(PLUGIN)
    (tmp_path / "_private.py").write_text("raise RuntimeError('not loaded')")
    found = registry.discover(plugin_dirs=[str(tmp_path)], use_entry_points=False)
    assert "studio.prefix" in found

    monkeypatch.setenv(registry.PLUGIN_PATH_ENV, str(tmp_path))
    assert "studio.prefix" in registry.discover(use_entry_points=False, builtins=False)


def test_missing_plugin_folder_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        registry.discover(plugin_dirs=[str(tmp_path / "missing")])


def test_entry_points_load_classes_and_modules(monkeypatch):
    def fake_entry_points(group):
        assert group == registry.ENTRY_POINT_GROUP
        return [_FakeEntryPoint(EntryPointCheck), _FakeEntryPoint(checks.uvs)]

    monkeypatch.setattr(importlib.metadata, "entry_points", fake_entry_points)
    found = registry.discover(builtins=False)
    assert found.ids() == ["ep.check", "uv.present", "uv.range"]


def test_duplicate_ids_and_invalid_classes_are_rejected():
    reg = registry.Registry()
    reg.register(EntryPointCheck)
    reg.register(EntryPointCheck)  # same class twice is fine

    class Clash(check.BaseCheck):
        id = "ep.check"

    with pytest.raises(ValueError):
        reg.register(Clash)

    class NoId(check.BaseCheck):
        pass

    class BadSeverity(check.BaseCheck):
        id = "bad"
        severity = "fatal"

    for cls in (NoId, BadSeverity, check.BaseCheck, object):
        with pytest.raises(TypeError):
            reg.register(cls)
    with pytest.raises(KeyError):
        reg.get("nope")


def test_config_disables_checks(tmp_path):
    instances = gate.load_checks({"disabled": ["uv.range", "lod.budget"]})
    ids = {c.id for c in instances}
    assert "uv.range" not in ids and "lod.budget" not in ids
    assert len(ids) == 13
