import json
import subprocess
from pathlib import Path

from klapcontext.agent_setup import (
    END,
    START,
    AgentInstructionsManager,
    context_freshness,
    doctor_agent,
    generate_mcp_configs,
    marker_state,
)


def context(name="sample"):
    return {
        "project": {"name": name},
        "stack": {"languages": ["PHP"], "frameworks": ["Laravel"]},
        "system_model": {
            "purpose": {"text": "Processes customer orders."},
            "main_flows": [{"name": "POST /orders"}],
        },
    }


def git_repo(path: Path) -> Path:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.test"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    (path / "README.md").write_text("sample")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=path, check=True, capture_output=True)
    return path


def generated_files(root: Path) -> None:
    for relative in (".klap/agent-context.md", ".klap/context.json", ".klap/index.html", ".klap/graphify/graph.json"):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}" if path.suffix == ".json" else "generated")


def test_create_private_agents_is_specific_idempotent_and_excluded(tmp_path):
    root = git_repo(tmp_path)
    result = AgentInstructionsManager(root).apply(context())
    text = (root / "AGENTS.md").read_text()
    assert result.created and "sample" in text and "Processes customer orders" in text
    assert ".klap/agent-context.md" in text and text.count(START) == 1
    assert "AGENTS.md" in (root / ".git/info/exclude").read_text().splitlines()
    second = AgentInstructionsManager(root).apply(context())
    assert second.status == "unchanged" and (root / "AGENTS.md").read_text().count(START) == 1


def test_merge_and_update_only_managed_block(tmp_path):
    root = git_repo(tmp_path)
    original = "# Team rules\n\nKeep this forever.\n"
    (root / "AGENTS.md").write_text(original)
    manager = AgentInstructionsManager(root)
    manager.apply(context("first"))
    manager.apply(context("second"))
    text = (root / "AGENTS.md").read_text()
    assert "Keep this forever" in text and "Repository `second`" in text and "Repository `first`" not in text
    assert text.count(START) == text.count(END) == 1
    assert (root / ".klap/backups/AGENTS.md").exists()


def test_malformed_markers_are_never_modified(tmp_path):
    path = tmp_path / "AGENTS.md"
    broken = f"Rules\n{START}\nbroken"
    path.write_text(broken)
    result = AgentInstructionsManager(tmp_path).apply(context())
    assert result.status == "conflict" and path.read_text() == broken
    assert marker_state(path.read_text()) == "malformed"


def test_tracked_agents_requires_permission_in_private_mode(tmp_path):
    root = git_repo(tmp_path)
    (root / "AGENTS.md").write_text("# Team")
    subprocess.run(["git", "add", "AGENTS.md"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "agents"], cwd=root, check=True, capture_output=True)
    blocked = AgentInstructionsManager(root).apply(context())
    assert blocked.status == "authorization_required" and (root / "AGENTS.md").read_text() == "# Team"
    allowed = AgentInstructionsManager(root).apply(context(), allow_tracked=True)
    assert allowed.status == "configured" and START in (root / "AGENTS.md").read_text()


def test_shared_mode_is_versionable_and_contains_bootstrap_without_personal_path(tmp_path):
    root = git_repo(tmp_path)
    manager = AgentInstructionsManager(root)
    manager.apply(context())
    assert "AGENTS.md" in (root / ".git/info/exclude").read_text()
    result = manager.apply(context(), shared=True)
    text = (root / "AGENTS.md").read_text()
    assert result.mode == "shared" and "If `.klap/` is missing, run `klap init`" in text
    assert str(root) not in text
    assert "AGENTS.md" not in (root / ".git/info/exclude").read_text().splitlines()


def test_mcp_config_and_doctor_report_real_files(tmp_path, monkeypatch):
    root = git_repo(tmp_path)
    generated_files(root)
    monkeypatch.setattr("klapcontext.agent_setup.command_prefix", lambda: ["python", "-m", "graphify"])
    config = generate_mcp_configs(root)
    AgentInstructionsManager(root).apply(context())
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True, check=True).stdout.strip()
    (root / ".klap/state.json").write_text(json.dumps({"git_commit": head}))
    result = doctor_agent(root)
    assert config["available"] and result["agents"]["valid"]
    assert result["context"]["available"] and result["graph"]["available"]
    assert result["mcp"]["configured"] and result["freshness"]["status"] == "CURRENT"


def test_context_freshness_detects_relevant_change_but_ignores_agents(tmp_path):
    root = git_repo(tmp_path)
    (root / ".klap").mkdir()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True, check=True).stdout.strip()
    (root / ".klap/state.json").write_text(json.dumps({"git_commit": head}))
    (root / "AGENTS.md").write_text("local")
    assert context_freshness(root)["status"] == "CURRENT"
    (root / "README.md").write_text("changed")
    assert context_freshness(root)["status"] == "STALE"
