import json
from pathlib import Path

from klapcontext import cli
from klapcontext.agent.capabilities import Capability, CapabilityRouter, default_providers
from klapcontext.agent.planner import ContextPlanner
from klapcontext.agent_context import render as render_agent
from klapcontext.context_builder import build
from klapcontext.detector import detect_components, detect_project
from klapcontext.git import exclude_klap
from klapcontext.portal import render as render_portal
from klapcontext.providers.code_intelligence import PhpCodeIntelligenceProvider
from klapcontext.frameworks.generic_php import GenericPhpAdapter
from klapcontext.frameworks.laravel import LaravelAdapter
from klapcontext.frameworks.fastapi import FastAPIAdapter
from klapcontext.frameworks.node import NodeAdapter
from klapcontext.agent.compiler import compile_context


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


def test_laravel_analysis_includes_versions_components_and_navigable_evidence(tmp_path):
    root = fixture_repo(tmp_path)
    (root / "composer.json").write_text(json.dumps({"require": {"php": "^8.2", "laravel/framework": "^11.0", "guzzlehttp/guzzle": "^7.0", "laravel/sanctum": "^4.0"}, "require-dev": {"pestphp/pest": "^3.0"}}))
    (root / "routes" / "api.php").write_text("<?php\nRoute::post('/orders', [OrderController::class, 'store']);\n")
    for folder, name in (("app/Http/Controllers", "OrderController"), ("app/Services", "OrderService"), ("app/Repositories", "OrderRepository"), ("app/Models", "Order"), ("app/Events", "OrderCreated"), ("app/Listeners", "SyncOrder")):
        path = root / folder; path.mkdir(parents=True, exist_ok=True)
        (path / f"{name}.php").write_text(f"<?php class {name} {{}}")
    context = build(root, {"nodes": []})
    system = context["system_model"]
    assert system["framework"]["version"] == "^11.0"
    assert system["framework"]["php_version"] == "^8.2"
    assert {item["category"] for item in system["dependencies"]} >= {"framework", "http", "authentication", "testing"}
    assert {item["type"] for item in system["components"]} >= {"controller", "service", "repository", "model"}
    route = system["routes"][0]
    assert route["line"] == 2 and route["evidence"][0]["line"] == 2
    assert route["evidence"][0]["snippet"] == "Route::post('/orders', [OrderController::class, 'store']);"
    assert len(system["events"]) == 1 and len(system["listeners"]) == 1
    page = render_portal(context, render_agent(context), [])
    assert "Laravel ^11.0" in page and "PHP ^8.2" in page


def test_agent_planner_selects_only_change_capabilities_for_authentication():
    plan = ContextPlanner().plan("Quiero modificar autenticación JWT", detail="standard", max_tokens=1200)
    assert plan.intent == "CHANGE" and plan.area == "authentication"
    assert "entry_point_discovery" in plan.capabilities
    assert "integration_discovery" not in plan.capabilities
    symbol = next(item for item in plan.providers if item["capability"] == "symbol_lookup")
    assert symbol["status"] == "READY" and symbol["provider"] == "php-tree-sitter"


def test_capability_router_uses_available_fallback_without_breaking_plan():
    router = CapabilityRouter(default_providers(graphify_ready=False))
    resolution = router.resolve(Capability.DEPENDENCY_GRAPH)
    assert resolution.status == "UNAVAILABLE" and resolution.provider is None
    plan = ContextPlanner(router).plan("¿Qué hace este sistema?", detail="minimal", max_tokens=500)
    assert plan.intent == "UNDERSTAND" and len(plan.sections) < 6


def test_php_code_intelligence_discovers_symbols_and_relations():
    root = Path(__file__).parent / "fixtures" / "php_code_intelligence"
    provider = PhpCodeIntelligenceProvider(root)
    service = provider.find_symbol("AuthService::authenticate")[0]
    assert service["file"] == "app/Services/AuthService.php"
    assert service["namespace"] == "App\\Services" and service["parent"] == "App\\Services\\AuthService"
    assert {item["type"] for item in provider.index()["symbols"]} >= {"class", "trait", "method", "constructor"}
    assert any(item["relation"] == "EXTENDS" for item in provider.index()["relations"])
    assert any(item["relation"] == "IMPLEMENTS" for item in provider.index()["relations"])


def test_php_code_intelligence_callers_graph_impact_and_minimal_context():
    root = Path(__file__).parent / "fixtures" / "php_code_intelligence"
    provider = PhpCodeIntelligenceProvider(root)
    callers = provider.callers("AuthService::authenticate")
    assert callers[0]["source_symbol"].endswith("AuthController::login")
    graph = provider.call_graph("AuthController::login", depth=3)
    targets = {item["target_symbol"] for item in graph["edges"]}
    assert "AuthService::authenticate" in targets and "JwtService::createToken" in targets and "AuditLogger::log" in targets
    impact = provider.impact("AuthService::authenticate")
    assert impact["direct_callers"] and impact["related_tests"] == ["tests/Feature/AuthTest.php"]
    context = provider.minimal_edit_context("AuthService::authenticate", max_tokens=300)
    assert "function authenticate" in context["source"]
    assert "JwtService::createToken" in {item["target_symbol"] for item in context["callees"]}


def test_php_code_intelligence_reuses_cache_and_registers_provider():
    root = Path(__file__).parent / "fixtures" / "php_code_intelligence"
    provider = PhpCodeIntelligenceProvider(root)
    first = provider.index()
    assert provider.cache_file.exists() and provider.index()["fingerprint"] == first["fingerprint"]
    resolution = CapabilityRouter(default_providers()).resolve(Capability.CALL_GRAPH)
    assert resolution.provider == "php-tree-sitter" and resolution.status == "READY"


def test_generic_php_adapter_keeps_analysis_useful_without_framework():
    root = Path(__file__).parent / "fixtures" / "php_generic"
    model = GenericPhpAdapter().analyze(root).as_dict()
    assert model["framework"] is None and model["analysis_mode"] == "GENERIC"
    assert any(item["name"] == "main" for item in model["entry_points"])
    assert any(item["type"] == "CALL" for item in model["transitions"])
    context = build(root, {"nodes": []})
    assert context["system_model"]["semantic_model"]["analysis_mode"] == "GENERIC"
    assert context["flows"]


def test_laravel_adapter_emits_generic_entries_and_semantic_transitions():
    root = Path(__file__).parent / "fixtures" / "laravel_semantic"
    model = LaravelAdapter().analyze(root).as_dict()
    endpoint = next(item for item in model["entry_points"] if item["type"] == "HTTP")
    assert endpoint["method"] == "POST" and endpoint["path"] == "/orders"
    kinds = {item["type"] for item in model["transitions"]}
    assert {"HTTP_ENTRY", "CALL", "QUEUE_DISPATCH", "EXTERNAL_CALL"} <= kinds
    flows = build(root, {"nodes": []})["flows"]
    assert any(any("OrderService::create" in step["name"] for step in flow["steps"]) for flow in flows)


def test_fastapi_adapter_uses_the_same_generic_entry_point_model():
    root = Path(__file__).parent / "fixtures" / "fastapi_semantic"
    model = FastAPIAdapter().analyze(root).as_dict()
    endpoint = model["entry_points"][0]
    assert endpoint["type"] == "HTTP" and endpoint["method"] == "POST" and endpoint["path"] == "/orders"
    context = build(root, {"nodes": []})
    assert context["semantic_model"]["framework"] == "FastAPI" and context["flows"]


def test_express_adapter_emits_generic_http_entry_point():
    root = Path(__file__).parent / "fixtures" / "express_semantic"
    model = NodeAdapter("Express").analyze(root).as_dict()
    assert model["entry_points"][0]["name"] == "POST /orders"
    assert build(root, {"nodes": []})["semantic_model"]["framework"] == "Express"


def test_detect_components_finds_multiple_subprojects():
    root = Path(__file__).parent / "fixtures" / "monorepo"
    components = detect_components(root)
    assert {item["path"] for item in components} == {"backend", "frontend"}


def test_context_compiler_ranks_compact_task_context():
    root = Path(__file__).parent / "fixtures" / "laravel_semantic"
    minimal = compile_context(root, "modificar orders", detail="minimal", max_tokens=400)
    deep = compile_context(root, "modificar orders", detail="deep", max_tokens=5000)
    assert minimal["intent"] == "CHANGE" and minimal["estimated_tokens"] <= 400
    assert len(minimal["read_first"]) <= len(deep["read_first"])
