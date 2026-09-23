import json
from pathlib import Path
from klapcontext.agent_context import render as render_agent
from klapcontext.context_builder import build
from klapcontext.detector import detect_project
from klapcontext.git import exclude_klap
from klapcontext.portal import render as render_portal
from klapcontext import cli

def fixture_repo(tmp_path):
    (tmp_path/".git"/"info").mkdir(parents=True)
    (tmp_path/"composer.json").write_text(json.dumps({"require":{"laravel/framework":"^11.0"}}))
    (tmp_path/"Dockerfile").write_text("FROM php:8.3")
    (tmp_path/"routes").mkdir(); (tmp_path/"routes"/"api.php").write_text("<?php")
    (tmp_path/"tests").mkdir()
    return tmp_path

def test_detector_collects_confirmed_evidence(tmp_path):
    root=fixture_repo(tmp_path); stack, evidence=detect_project(root)
    assert "Laravel" in stack["frameworks"] and "Docker" in stack["infrastructure"]
    assert all(x.status == "CONFIRMED" for x in evidence)

def test_context_agent_and_portal(tmp_path):
    root=fixture_repo(tmp_path); context=build(root, {"nodes":[{"name":"UserController","path":"app/Http/UserController.php","type":"controller"}]})
    assert context["schema_version"] == "0.2" and context["architecture"]["status"] == "INFERRED"
    agent=render_agent(context); page=render_portal(context, agent, ["graph.html"])
    assert "Instrucciones para el Agente" in agent and "Copiar contexto" in page and "Abrir grafo técnico" in page

def test_exclude_klap_is_idempotent(tmp_path, monkeypatch):
    root=fixture_repo(tmp_path)
    monkeypatch.setattr("klapcontext.git.run_git", lambda root,*args: ".git" if args == ("rev-parse", "--git-dir") else "true")
    exclude_klap(root); exclude_klap(root)
    assert (root/".git/info/exclude").read_text().splitlines().count(".klap/") == 1

def test_status_marks_matching_clean_context_current(tmp_path, monkeypatch, capsys):
    (tmp_path/".klap").mkdir()
    (tmp_path/".klap"/"state.json").write_text(json.dumps({"git_commit":"abc"}))
    monkeypatch.setattr(cli, "commit", lambda root: "abc")
    monkeypatch.setattr(cli, "dirty_files", lambda root: [])
    assert cli.cmd_status(type("Args", (), {"path":str(tmp_path)})()) == 0
    assert "CURRENT" in capsys.readouterr().out

def test_system_model_reads_docs_routes_scheduler_and_deployment(tmp_path):
    root=fixture_repo(tmp_path)
    (root/"README.md").write_text("# Contact processor\n\nProcesses customer audio through a local API.")
    (root/"routes"/"api.php").write_text("Route::post('/audio', [AudioController::class, 'store']);")
    (root/"routes"/"console.php").write_text("Schedule::command('audio:send')->everyThirtyMinutes();")
    (root/"docker-compose.yml").write_text("services:\n  app:\n    ports: ['8010:80']")
    context=build(root, {"nodes":[]}); system=context["system_model"]
    assert system["purpose"]["text"] == "Processes customer audio through a local API."
    assert any(item["type"] == "http" for item in system["entry_points"])
    assert system["background_processes"] and "Docker Compose" in system["deployment"]["tools"]
    assert any(item["intent"] == "Entender la API HTTP" for item in system["start_here"])
