import asyncio
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

from klapcontext.agent_setup import doctor_agent, probe_graphify_mcp
from klapcontext.freshness import evaluate_freshness
from klapcontext.frameworks.fastapi import FastAPIAdapter
from klapcontext.frameworks.laravel import LaravelAdapter, analyze as analyze_laravel
from klapcontext.frameworks.node import NodeAdapter
from klapcontext.graphify import canonical_graph, generate as generate_graph, migrate_legacy_graphs
from klapcontext.scope import IndexScope, RULES_VERSION
from klapcontext.providers.code_intelligence import PhpCodeIntelligenceProvider


def init_git(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.test"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)


def test_next_scope_prioritizes_owned_code_and_keeps_custom_public_js(tmp_path):
    files = {
        "package.json": '{"dependencies":{"next":"10.0.0"}}',
        "pages/index.js": "export default function Home() {}",
        "components/Card.jsx": "export const Card = () => null",
        "context/CRMContext.js": "export const CRMContext = {}",
        "lib/api.ts": "export const api = 1",
        ".next/server/pages/index.js": "compiled",
        "node_modules/pkg/index.js": "vendor",
        "public/assets/vendor/jquery.js": "vendor",
        "public/custom/runtime.js": "owned public code",
        "public/downloaded.html": "<html>legitimate project resource</html>",
    }
    for relative, content in files.items():
        path = tmp_path / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content)
    scope = IndexScope.load(tmp_path)
    included = scope.included_paths
    assert {"pages/index.js", "components/Card.jsx", "context/CRMContext.js", "lib/api.ts", "public/custom/runtime.js"} <= included
    assert not any(path.startswith((".next/", "node_modules/", "public/assets/vendor/")) for path in included)
    assert "public/downloaded.html" not in included
    graph = {"nodes": [
        {"id": "crm", "source_file": "context/CRMContext.js"},
        {"id": "compiled", "source_file": ".next/server/pages/index.js"},
        {"id": "vendor", "source_file": "node_modules/pkg/index.js"},
    ], "links": []}
    filtered = scope.filter_graph(graph)
    assert [node["id"] for node in filtered["nodes"]] == ["crm"]


def test_scope_honors_explicit_exceptions_and_exclusions(tmp_path):
    init_git(tmp_path)
    (tmp_path / ".gitignore").write_text("vendor/\n")
    for relative in ("src/app.py", "vendor/internal/owned.py"):
        path = tmp_path / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_text("pass")
    (tmp_path / ".klap").mkdir()
    (tmp_path / ".klap/scope.json").write_text(json.dumps({"version": 1, "include": ["vendor/internal/owned.py"], "exclude": ["src/**"]}))
    scope = IndexScope.load(tmp_path)
    assert scope.included_paths == {"vendor/internal/owned.py"}
    assert "!vendor/internal/owned.py" in scope.graphify_excludes()


def test_laravel_routes_ignore_comments_and_string_examples(tmp_path):
    (tmp_path / "composer.json").write_text('{"require":{"laravel/framework":"^11.0"}}')
    routes = tmp_path / "routes"; routes.mkdir()
    (routes / "api.php").write_text("""<?php
Route::get('/active', [ActiveController::class, 'show']);
// Route::get('/line', [FakeController::class, 'show']);
# Route::get('/hash', [FakeController::class, 'show']);
/* Route::get('/block', [FakeController::class, 'show']); */
$example = "Route::get('/string', [FakeController::class, 'show']);";
""")
    result = analyze_laravel(tmp_path)
    assert [item["name"] for item in result["routes"]] == ["GET /active"]
    assert len(result["disabled_declarations"]) == 4


def test_laravel_scheduler_counts_only_active_code_and_records_disabled(tmp_path):
    (tmp_path / "composer.json").write_text('{"require":{"laravel/framework":"^11.0"}}')
    routes = tmp_path / "routes"; routes.mkdir()
    (routes / "console.php").write_text("""<?php
Schedule::command('fetch:audio-metadata')->cron('0,30 * * * *');
// Schedule::command('comment-one')->hourly();
# Schedule::command('comment-two')->daily();
/* Schedule::command('comment-three')->weekly(); */
/*
Schedule::command('comment-four')->monthly();
Schedule::command('comment-five')->yearly();
*/
$example = "Schedule::command('string-example')->everyMinute();";
""")
    result = analyze_laravel(tmp_path)
    assert [item["name"] for item in result["scheduled_processes"]] == ["fetch:audio-metadata"]
    assert result["scheduled_processes"][0]["schedule"] == "cron"
    assert len(result["disabled_declarations"]) == 6
    assert {item.get("name") for item in result["disabled_declarations"]} >= {"comment-one", "comment-five", "string-example"}
    assert all(item["status"] == "commented_or_disabled" for item in result["disabled_declarations"])


def test_laravel_relations_distinguish_injection_dispatch_and_listener(tmp_path):
    (tmp_path / "composer.json").write_text('{"require":{"laravel/framework":"^11.0"}}')
    files = {
        "routes/api.php": "<?php Route::post('/batch', [BatchController::class, 'store']);",
        "app/Http/Controllers/BatchController.php": "<?php namespace App\\Http\\Controllers; use App\\Services\\ReprocessService; class BatchController { public function __construct(private ReprocessService $service) {} public function store(){ return $this->service->run(); }}",
        "app/Services/ReprocessService.php": "<?php namespace App\\Services; use App\\Jobs\\SendBatchJob; use App\\Events\\BatchReprocessed; class ReprocessService { public function run(){ SendBatchJob::dispatch(); event(new BatchReprocessed()); }}",
        "app/Jobs/SendBatchJob.php": "<?php namespace App\\Jobs; class SendBatchJob implements ShouldQueue { public function handle(){} }",
        "app/Events/BatchReprocessed.php": "<?php namespace App\\Events; class BatchReprocessed {}",
        "app/Listeners/SendBatch.php": "<?php namespace App\\Listeners; use App\\Events\\BatchReprocessed; use App\\Services\\ReprocessService; class SendBatch { public function __construct(private ReprocessService $service) {} public function handle(BatchReprocessed $event){} }",
    }
    for relative, content in files.items():
        path = tmp_path / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content)
    model = LaravelAdapter(IndexScope.load(tmp_path)).analyze(tmp_path).as_dict()
    relations = {(item["type"], item["source"].split("\\")[-1], item["target"].split("\\")[-1]) for item in model["transitions"]}
    assert any(kind == "INJECTS" and target == "ReprocessService" for kind, _, target in relations)
    assert any(kind == "DISPATCHES" and target in {"SendBatchJob", "BatchReprocessed"} for kind, _, target in relations)
    assert ("LISTENS_TO", "SendBatch", "BatchReprocessed") in relations
    impact = PhpCodeIntelligenceProvider(tmp_path, IndexScope.load(tmp_path)).impact("ReprocessService")
    assert any(path["from"].endswith("BatchController::store") for path in impact["relationship_paths"])


def test_node_routes_ignore_comments_and_string_examples(tmp_path):
    (tmp_path / "package.json").write_text('{"dependencies":{"express":"1"}}')
    (tmp_path / "app.js").write_text("""app.get('/active', handler);
// app.get('/line', fake);
/* app.get('/block', fake); */
const example = "app.get('/string', fake);";
""")
    model = NodeAdapter("Express", IndexScope.load(tmp_path)).analyze(tmp_path)
    assert [entry.name for entry in model.entry_points] == ["GET /active"]


def test_scope_preserves_fastapi_nest_and_dotnet_sources(tmp_path):
    files = {
        "api/main.py": "from fastapi import FastAPI\napp=FastAPI()\n@app.get('/ok')\ndef ok(): return True",
        "api/requirements.txt": "fastapi",
        "nest/src/app.controller.ts": "@Controller('x')\nexport class X { @Get('ok') ok(){} }",
        "nest/package.json": '{"dependencies":{"@nestjs/core":"1"}}',
        "dotnet/Api.csproj": "<Project />",
        "dotnet/Controllers/WeatherController.cs": "class WeatherController {}",
        "dotnet/bin/Debug/net8.0/Api.dll": "binary",
        "dotnet/obj/Debug/generated.cs": "class Generated {}",
    }
    for relative, content in files.items():
        path = tmp_path / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content)
    scope = IndexScope.load(tmp_path)
    assert {"api/main.py", "nest/src/app.controller.ts", "dotnet/Controllers/WeatherController.cs"} <= scope.included_paths
    assert "dotnet/obj/Debug/generated.cs" not in scope.included_paths
    api_root = tmp_path / "api"; api_scope = IndexScope.load(api_root)
    nest_root = tmp_path / "nest"; nest_scope = IndexScope.load(nest_root)
    assert FastAPIAdapter(api_scope).analyze(api_root).entry_points
    assert NodeAdapter("NestJS", nest_scope).analyze(nest_root).entry_points


def test_canonical_graph_generation_passes_scope_before_provider(tmp_path, monkeypatch):
    (tmp_path / "app.py").write_text("def main(): pass")
    scope = IndexScope.load(tmp_path)
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        if "extract" in command:
            graph = canonical_graph(tmp_path)
            graph.parent.mkdir(parents=True, exist_ok=True)
            graph.write_text('{"nodes":[],"links":[]}')
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("klapcontext.graphify.command_prefix", lambda: ["graphify"])
    monkeypatch.setattr("klapcontext.graphify.subprocess.run", fake_run)
    result = generate_graph(tmp_path, scope=scope)
    extract = commands[0]
    assert result == tmp_path / ".klap/graphify-out/graph.json"
    assert "--exclude" in extract and "--out" in extract
    assert not (tmp_path / "graphify-out/graph.json").exists()


def write_snapshot(root: Path) -> None:
    scope = IndexScope.load(root)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True, check=True).stdout.strip()
    (root / ".klap/state.json").write_text(json.dumps({"git_commit": head, "scope": {"rules_version": RULES_VERSION, "hash": scope.snapshot_hash()}}))


def test_freshness_is_identical_for_status_and_doctor_inputs(tmp_path):
    init_git(tmp_path)
    (tmp_path / "app.py").write_text("print('ok')")
    subprocess.run(["git", "add", "app.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "app"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / ".klap").mkdir()
    for relative in ("agent-context.md", "context.json", "index.html", "graphify-out/graph.json", "mcp/generic.json", "mcp/codex.toml"):
        path = tmp_path / ".klap" / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_text("{}")
    (tmp_path / "AGENTS.md").write_text("<!-- KLAPCONTEXT:START -->\n<!-- KLAPCONTEXT:END -->")
    write_snapshot(tmp_path)
    assert evaluate_freshness(tmp_path) == doctor_agent(tmp_path)["freshness"]
    (tmp_path / "app.py").write_text("print('changed')")
    assert evaluate_freshness(tmp_path)["status"] == doctor_agent(tmp_path)["freshness"]["status"] == "STALE"


def test_mcp_probe_reports_missing_command(tmp_path, monkeypatch):
    graph = tmp_path / ".klap/graphify-out/graph.json"; graph.parent.mkdir(parents=True); graph.write_text('{"nodes":[],"links":[]}')
    monkeypatch.setattr("klapcontext.agent_setup.importlib.util.find_spec", lambda name: None)
    result = probe_graphify_mcp(tmp_path)
    assert not result["connection_verified"] and "no está instalado" in result["reason"]


def test_mcp_probe_reports_missing_graph_and_handshake_failure(tmp_path, monkeypatch):
    missing = probe_graphify_mcp(tmp_path)
    assert not missing["connection_verified"] and not missing["stages"]["graph_present"]["ok"]
    graph = tmp_path / ".klap/graphify-out/graph.json"; graph.parent.mkdir(parents=True); graph.write_text('{"nodes":[],"links":[]}')

    async def failed(_graph):
        raise RuntimeError("handshake rejected")

    monkeypatch.setattr("klapcontext.agent_setup._probe_graphify_mcp_async", failed)
    result = probe_graphify_mcp(tmp_path)
    assert not result["connection_verified"] and "RuntimeError" in result["reason"]


def test_mcp_probe_reports_timeout(tmp_path, monkeypatch):
    graph = tmp_path / ".klap/graphify-out/graph.json"; graph.parent.mkdir(parents=True); graph.write_text('{"nodes":[],"links":[]}')

    async def slow(_graph):
        await asyncio.sleep(1)
        return {}

    monkeypatch.setattr("klapcontext.agent_setup._probe_graphify_mcp_async", slow)
    result = probe_graphify_mcp(tmp_path, timeout=0.01)
    assert not result["connection_verified"] and "timed out" in result["reason"]


def test_legacy_graph_migration_is_explicit_and_preserves_unknown_data(tmp_path):
    canonical = tmp_path / ".klap/graphify-out/graph.json"; canonical.parent.mkdir(parents=True); canonical.write_text('{"nodes":[],"links":[]}')
    local = tmp_path / ".klap/graphify"; local.mkdir(); (local / "graph.json").write_text('{"nodes":[{"id":"old"}]}')
    unknown = tmp_path / "graphify-out"; unknown.mkdir(); (unknown / "graph.json").write_text('{"nodes":[{"id":"user"}]}')
    planned = migrate_legacy_graphs(tmp_path)
    assert planned["planned"] == [".klap/graphify"] and local.exists() and unknown.exists()
    migrated = migrate_legacy_graphs(tmp_path, apply=True)
    assert migrated["status"] == "migrated" and not local.exists() and unknown.exists()
    assert migrated["moved"][0]["to"].startswith(".klap/backups/")


@pytest.mark.skipif(importlib.util.find_spec("graphify.serve") is None, reason="Graphify not installed")
def test_real_graphify_mcp_handshake_and_minimal_query(tmp_path):
    graph = tmp_path / ".klap/graphify-out/graph.json"; graph.parent.mkdir(parents=True)
    graph.write_text(json.dumps({"nodes": [{"id": "n1", "label": "main", "type": "function", "source_file": "app.py"}], "links": []}))
    result = probe_graphify_mcp(tmp_path, timeout=15)
    assert result["connection_verified"]
    assert result["stages"]["tool_discovery"]["ok"] and result["stages"]["minimal_query"]["ok"]
