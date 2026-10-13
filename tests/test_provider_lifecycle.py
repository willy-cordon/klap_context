import json
import subprocess
from pathlib import Path

from klapcontext import cli
from klapcontext.providers.lifecycle import GRAPHIFY, ProviderLifecycle, ProviderRuntime


def test_project_configuration_disables_provider_before_any_install(tmp_path, monkeypatch):
    config = tmp_path / ".klap" / "providers.json"
    config.parent.mkdir()
    config.write_text(json.dumps({"providers": {"graphify": {"enabled": False}}}), encoding="utf-8")
    lifecycle = ProviderLifecycle(tmp_path)
    monkeypatch.setattr(lifecycle, "_install", lambda *_: (_ for _ in ()).throw(AssertionError("must not install")))
    result = lifecycle.prepare(no_serena=True)
    assert result["graphify"]["state"] == "SKIPPED"
    assert result["graphify"]["source"] == "project configuration"


def test_cli_opt_out_is_recorded_without_installing(tmp_path, monkeypatch):
    lifecycle = ProviderLifecycle(tmp_path)
    monkeypatch.setattr(lifecycle, "_install", lambda *_: (_ for _ in ()).throw(AssertionError("must not install")))
    result = lifecycle.prepare(no_graphify=True, no_serena=True)
    assert {value["state"] for value in result.values()} == {"SKIPPED"}
    assert (tmp_path / ".klap" / "provider-state.json").exists()


def test_failed_managed_install_is_reported_and_does_not_raise(tmp_path, monkeypatch):
    lifecycle = ProviderLifecycle(tmp_path)
    monkeypatch.setattr("klapcontext.providers.lifecycle.shutil.which", lambda _: None)

    def failed(*_args, **_kwargs):
        raise subprocess.CalledProcessError(1, ["pip"], stderr="offline")

    monkeypatch.setattr("klapcontext.providers.lifecycle.subprocess.run", failed)
    result = lifecycle._ensure("graphify", GRAPHIFY, skip=False, repair=False)
    assert result.state == "FAILED"
    assert "offline" in (result.error or "")


def test_compatible_existing_provider_is_not_reinstalled(tmp_path, monkeypatch):
    lifecycle = ProviderLifecycle(tmp_path)
    monkeypatch.setattr("klapcontext.providers.lifecycle.shutil.which", lambda command: f"/tools/{command}")
    monkeypatch.setattr("klapcontext.providers.lifecycle._version", lambda *_: "0.9.66")
    monkeypatch.setattr(lifecycle, "_graphify_healthy", lambda _: True)
    monkeypatch.setattr(lifecycle, "_install", lambda *_: (_ for _ in ()).throw(AssertionError("must not reinstall")))
    result = lifecycle._ensure("graphify", GRAPHIFY, skip=False, repair=False)
    assert result.state == "READY" and result.source == "system"


def test_serena_without_uv_is_repaired_in_an_isolated_runtime(tmp_path, monkeypatch):
    lifecycle = ProviderLifecycle(tmp_path)
    monkeypatch.setattr("klapcontext.providers.lifecycle.shutil.which", lambda command: f"/tools/{command}" if command == "serena" else None)
    monkeypatch.setattr("klapcontext.providers.lifecycle._version", lambda *_: "1.7.0")
    monkeypatch.setattr(lifecycle, "_serena_has_uv", lambda _source: False)
    expected = ProviderRuntime("serena", "1.7.0", "READY", "1.7.0", "managed", "/runtime/serena")
    called = []
    monkeypatch.setattr(lifecycle, "_install", lambda *args: called.append(args) or expected)
    monkeypatch.setattr(lifecycle, "_verify", lambda runtime: runtime)
    assert lifecycle._ensure("serena", {"version": "1.7.0", "command": "serena", "series": (1, 7)}, skip=False, repair=False) is expected
    assert called


def test_init_flags_are_forwarded_to_generation(tmp_path, monkeypatch):
    seen = {}

    def generated(root, **kwargs):
        seen.update(kwargs)
        return {"providers": {"dependency_graph": {}}, "analysis": {"providers": [], "status": "COMPLETE"}, "agent_onboarding": {}, "system_model": {"exploration": {"coverage": {"code_files_with_graph_nodes": 0, "eligible_code_files": 0, "status": "EMPTY"}}, "index_scope": {"included_code_files": 0, "excluded_files": 0, "rules_version": 1}}, "project": {"name": "fixture"}, "stack": {}}

    monkeypatch.setattr(cli, "generate_all", generated)
    args = type("Args", (), {"path": str(tmp_path), "no_graphify": True, "no_serena": True})()
    assert cli.cmd_init(args) == 0
    assert seen["no_graphify"] is True and seen["no_serena"] is True


def test_doctor_repair_prepares_standard_providers(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "prepare_standard_providers", lambda root, repair: {"graphify": {"state": "READY", "connection": "VERIFIED"}})
    monkeypatch.setattr(cli, "doctor_agent", lambda root, probe_mcp: {
        "agents": {"valid": True, "missing_paths": []},
        "context": {"available": True},
        "freshness": {"status": "CURRENT"},
        "graph": {"available": True, "required": False, "legacy_duplicates": []},
        "mcp": {"configured": True, "required": False, "connection_verified": True, "stages": {}},
        "scope": {"included_code_files": 1, "excluded_files": 0, "warnings": []},
        "optional_providers": {},
    })
    args = type("Args", (), {"path": str(tmp_path), "repair": True, "probe_mcp": False})()
    assert cli.cmd_doctor(args) == 0
