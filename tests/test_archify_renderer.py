import json
import os
import subprocess
from pathlib import Path

import pytest

from klapcontext.archify import ArchifyResult, generate, project_flows, render, write_state
from klapcontext.portal import render as render_portal


def context_with_flow():
    return {
        "project": {"name": "fixture", "git_commit": "a" * 40, "repository_url": "https://example.test/fixture.git"},
        "stack": {},
        "evidence": [],
        "analysis": {"providers": []},
        "system_model": {
            "entry_points": [], "unknowns": [], "index_scope": {}, "exploration": {},
            "main_flows": [{
                "name": "POST /orders", "status": "INFERRED", "confidence": 0.72,
                "steps": [
                    {"name": "POST /orders", "kind": "http", "path": "routes\\api.php", "line": 4, "status": "CONFIRMED"},
                    {"name": "OrderController::store", "kind": "handler", "path": "app\\OrderController.php", "status": "CONFIRMED"},
                    {"name": "OrderService::create", "kind": "call", "path": "app/OrderService.php", "status": "INFERRED"},
                    {"name": "Audit::record", "kind": "event", "path": "app/Audit.php", "status": "INFERRED"},
                ],
                "edges": [
                    {"from": 0, "to": 1, "role": "main"},
                    {"from": 1, "to": 2, "role": "main"},
                    {"from": 1, "to": 3, "role": "branch", "label": "audit"},
                ],
            }],
            "purpose": {}, "framework": {}, "system_interactions": {}, "inputs": [], "outputs": [], "dependencies": [], "recent_changes": [],
        },
        "freshness": {"status": "CURRENT"},
    }


def test_projection_preserves_branch_evidence_confidence_and_limitations():
    projected = project_flows(context_with_flow())
    assert len(projected) == 1
    diagram = projected[0]
    assert diagram["confidence"] == 0.72 and diagram["status"] == "PARTIAL"
    assert any(edge["role"] == "branch" and edge["label"] == "audit" for edge in diagram["ir"]["edges"])
    assert diagram["ir"]["nodes"][0]["sources"] == [{"path": "routes/api.php", "label": "CONFIRMED", "line": 4}]
    assert "inferred static-analysis" in " ".join(diagram["limitations"])


def test_projection_does_not_invent_flow_without_two_related_steps():
    context = context_with_flow()
    context["system_model"]["main_flows"] = [{"name": "orphan", "steps": [{"name": "OnlyNode"}]}]
    assert project_flows(context) == []


def test_disabled_or_failed_renderer_does_not_remove_existing_context(tmp_path, monkeypatch):
    context = context_with_flow()
    disabled = generate(tmp_path, context, disabled=True)
    assert disabled["state"] == "SKIPPED"
    failed = render(tmp_path, context, ArchifyResult("FAILED", error="renderer unavailable"))
    assert failed.state == "FAILED" and context["system_model"]["main_flows"]


def test_failed_update_retains_previous_valid_diagram_as_stale(tmp_path, monkeypatch):
    output = tmp_path / ".klap" / "flows" / "flow.html"
    output.parent.mkdir(parents=True)
    output.write_text("valid", encoding="utf-8")
    write_state(tmp_path, ArchifyResult("READY", diagrams=[{"id": "flow", "html": "flows/flow.html", "limitations": []}]))
    monkeypatch.setattr("klapcontext.archify.prepare", lambda *args, **kwargs: ArchifyResult("FAILED", error="boom"))
    result = generate(tmp_path, context_with_flow())
    assert result["state"] == "FAILED" and result["diagrams"][0]["status"] == "STALE"
    assert output.read_text() == "valid"


def test_unexpected_renderer_error_is_normalized(tmp_path, monkeypatch):
    monkeypatch.setattr("klapcontext.archify.prepare", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("offline")))
    result = generate(tmp_path, context_with_flow())
    assert result["state"] == "FAILED" and "offline" in result["error"]


def test_portal_embeds_diagram_with_offline_relative_paths():
    context = context_with_flow()
    context["renderers"] = {"archify": {"state": "READY", "version": "3.1.0", "installed_version": "3.1.0", "diagrams": [{"title": "POST /orders", "entry_point": "POST /orders", "html": "flows/post-orders.html", "ir": "flows/post-orders.workflow.json", "status": "PARTIAL", "evidence": [{"path": "routes/api.php", "line": 4}], "limitations": ["static only"]}]}}
    page = render_portal(context, "agent", [])
    assert "id='diagram-frame'" in page and "src='flows/post-orders.html'" in page
    assert "https://" not in page and "Abrir por separado" in page


@pytest.mark.skipif(not os.environ.get("KLAP_ARCHIFY_RUNTIME"), reason="set KLAP_ARCHIFY_RUNTIME to an unpacked Archify 3.1.0 runtime")
def test_real_archify_310_renders_projected_fixture(tmp_path):
    runtime = Path(os.environ["KLAP_ARCHIFY_RUNTIME"])
    for relative in ("routes/api.php", "app/OrderController.php", "app/OrderService.php", "app/Audit.php"):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<?php\n// fixture\n// fixture\n// fixture\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "fixture@example.test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Fixture"], cwd=tmp_path, check=True)
    subprocess.run(["git", "remote", "add", "origin", "https://example.test/fixture.git"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=tmp_path, check=True)
    context = context_with_flow()
    context["project"]["git_commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True).strip()
    result = render(tmp_path, context, ArchifyResult("READY", executable=str(runtime / "bin" / "archify.mjs"), installed_version="3.1.0"))
    assert result.state == "READY" and result.diagrams
    html = tmp_path / ".klap" / result.diagrams[0]["html"]
    assert html.is_file() and "<!doctype html>" in html.read_text(encoding="utf-8").lower()
    source = tmp_path / ".klap" / result.diagrams[0]["ir"]
    assert json.loads(source.read_text())["diagram_type"] == "workflow"
