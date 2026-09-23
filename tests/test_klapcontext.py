import json

from klapcontext import cli
from klapcontext.agent_context import render as render_agent
from klapcontext.context_builder import build
from klapcontext.detector import detect_project
from klapcontext.git import exclude_klap
from klapcontext.portal import render as render_portal


def fixture_repo(tmp_path):
    (tmp_path / ".git" / "info").mkdir(parents=True)
    (tmp_path / "composer.json").write_text(json.dumps({"require": {"laravel/framework": "^11.0"}}))
    (tmp_path / "Dockerfile").write_text("FROM php:8.3")
    (tmp_path / "routes").mkdir()
    (tmp_path / "routes" / "api.php").write_text("<?php")
    return tmp_path


def test_detector_collects_confirmed_evidence(tmp_path):
    stack, evidence = detect_project(fixture_repo(tmp_path))
    assert "Laravel" in stack["frameworks"]
    assert "Docker" in stack["infrastructure"]
    assert all(item.status == "CONFIRMED" for item in evidence)


def test_portal_has_dashboard_and_real_views(tmp_path):
    context = build(fixture_repo(tmp_path), {"nodes": [{"name": "UserController", "path": "app/Http/UserController.php", "type": "controller"}]})
    page = render_portal(context, render_agent(context), ["graph.html"])
    assert "PANORAMA DEL SISTEMA" in page
    assert "Mapa del sistema" in page
    assert "data-view='flujos'" in page
    assert "data-go='evidencia'" in page
    assert "Copiar contexto" in page


def test_exclude_klap_is_idempotent(tmp_path, monkeypatch):
    root = fixture_repo(tmp_path)
    monkeypatch.setattr("klapcontext.git.run_git", lambda root, *args: ".git" if args == ("rev-parse", "--git-dir") else "true")
    exclude_klap(root)
    exclude_klap(root)
    assert (root / ".git" / "info" / "exclude").read_text().splitlines().count(".klap/") == 1


def test_status_marks_matching_clean_context_current(tmp_path, monkeypatch, capsys):
    (tmp_path / ".klap").mkdir()
    (tmp_path / ".klap" / "state.json").write_text(json.dumps({"git_commit": "abc"}))
    monkeypatch.setattr(cli, "commit", lambda root: "abc")
    monkeypatch.setattr(cli, "dirty_files", lambda root: [])
    assert cli.cmd_status(type("Args", (), {"path": str(tmp_path)})()) == 0
    assert "CURRENT" in capsys.readouterr().out


def test_laravel_adapter_detects_flow_and_map(tmp_path):
    root = fixture_repo(tmp_path)
    (root / "routes" / "api.php").write_text("Route::post('/users', [UserController::class, 'store']);")
    (root / "routes" / "console.php").write_text("Schedule::command('reports:send')->hourly();")
    commands = root / "app" / "Console" / "Commands"; commands.mkdir(parents=True)
    (commands / "SendReport.php").write_text("protected $signature = 'reports:send';")
    jobs = root / "app" / "Jobs"; jobs.mkdir(parents=True)
    (jobs / "GenerateReport.php").write_text("class GenerateReport implements ShouldQueue { public $queue = 'reports'; }")
    controller = root / "app" / "Http" / "Controllers"; controller.mkdir(parents=True)
    (controller / "UserController.php").write_text("class UserController { UserService $service; }")
    system = build(root, {"nodes": []})["system_model"]
    assert system["routes"][0]["target"] == "UserController::store"
    assert system["scheduled_processes"][0]["schedule"] == "hourly"
    assert system["queue_jobs"][0]["queue"] == "reports"
    assert system["main_flows"] and system["system_interactions"]["nodes"]
