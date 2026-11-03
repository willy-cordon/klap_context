"""Graph-first acceptance: provenance, offline packaging and retained agent APIs."""
import importlib.util
import json
import re
import subprocess
from pathlib import Path

import pytest

from klapcontext import cli
from klapcontext.portal import graph_data, render
from klapcontext.providers.lifecycle import ProviderLifecycle, ProviderRuntime
from klapcontext.providers.services import default_registry


def graph_fixture():
    return {"nodes": [
        {"id": "a", "label": "Controller", "type": "class", "source_file": "app/api.py", "line": 3},
        {"id": "b", "label": "save", "type": "function", "source_file": "app/store.py"},
        {"id": "c", "label": "unused", "type": "function"},
    ], "links": [{"source": "a", "target": "b", "relation": "calls"}]}


def test_portal_preserves_exact_graph_relations_and_escapes_untrusted_labels():
    graph = graph_fixture()
    graph["nodes"][0]["label"] = '</script><script>alert(1)</script>'
    page = render({"project": {"name": '<unsafe>'}}, '', [], graph=graph)
    data = json.loads(re.search(r'<script id="graph-data" type="application/json">(.*?)</script>', page, re.S)[1])
    assert data == graph_data(graph)
    assert [(e['from'], e['to'], e['relation']) for e in data['edges']] == [('a', 'b', 'calls')]
    assert '</script><script>alert(1)</script>' not in page
    assert '&lt;unsafe&gt;' in page
    assert not re.search(r'<script[^>]+src=', page)
    assert re.findall(r'<a href="([^"]+)"', page) == ['#inicio', '#historial']


def test_invalid_endpoints_and_duplicate_ids_do_not_create_relations():
    graph = graph_fixture()
    graph['nodes'] += [{'id': 'a'}, {'label': 'no id'}]
    graph['links'] += [{'source': 'a', 'target': 'missing'}]
    data = graph_data(graph)
    assert len(data['nodes']) == 3 and len(data['edges']) == 1
    assert graph_data({'graph': graph}) == data


def test_standard_lifecycle_only_prepares_graphify(tmp_path, monkeypatch):
    calls = []
    def ensure(name, spec, **kwargs):
        calls.append(name)
        return ProviderRuntime(name, spec['version'], 'READY')
    monkeypatch.setattr(ProviderLifecycle, '_ensure', lambda self, *a, **k: ensure(*a, **k))
    assert set(ProviderLifecycle(tmp_path).prepare()) == {'graphify'}
    assert calls == ['graphify']
    assert not {'serena', 'archify'} & {r.name for r in default_registry(tmp_path).registrations()}


@pytest.mark.parametrize('flag', ['--no-serena', '--no-archify'])
def test_removed_flags_are_not_silent_noops(flag):
    with pytest.raises(SystemExit) as result:
        cli.main(['init', flag])
    assert result.value.code == 2


def test_init_update_open_native_fallback_preserves_user_artifacts(tmp_path, monkeypatch):
    subprocess.run(['git', 'init', str(tmp_path)], check=True, capture_output=True)
    (tmp_path / 'app.py').write_text('def hello(): return 1\n')
    legacy = tmp_path / '.klap' / 'archify-state.json'
    legacy.parent.mkdir()
    legacy.write_text('user-owned legacy data')
    (legacy.parent / 'graphify-out').mkdir()
    (legacy.parent / 'graphify-out' / 'graph.json').write_text(json.dumps(graph_fixture()))
    monkeypatch.setattr(ProviderLifecycle, '_install', lambda *a: pytest.fail('unexpected installation'))
    assert cli.main(['init', str(tmp_path), '--no-graphify']) == 0
    first = json.loads((legacy.parent / 'state.json').read_text())
    (tmp_path / 'app.py').write_text('def changed(): return 2\n')
    assert cli.main(['update', str(tmp_path), '--no-graphify']) == 0
    second = json.loads((legacy.parent / 'state.json').read_text())
    assert first['scope']['hash'] != second['scope']['hash']
    assert legacy.read_text() == 'user-owned legacy data'
    page = (legacy.parent / 'index.html').read_text(encoding='utf-8')
    assert 'Grafo de Graphify no disponible' in page and 'id="graph-data"' not in page
    assert (tmp_path / 'AGENTS.md').exists()
    assert (legacy.parent / 'agent-context.md').exists()
    context = json.loads((legacy.parent / 'context.json').read_text())
    assert 'system_model' in context and 'evidence' in context
    opened = []
    monkeypatch.setattr(cli.webbrowser, 'open', opened.append)
    assert cli.main(['open', str(tmp_path)]) == 0
    assert opened == [(legacy.parent / 'index.html').as_uri()]


def test_own_mcp_remains_callable_without_retired_adapters(tmp_path):
    spec = importlib.util.spec_from_file_location('graph_first_mcp', Path(__file__).parents[1] / 'mcp_server.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    (tmp_path / 'app.py').write_text('def greet(name): return name\n')
    result = module.klap_search_symbols('greet', path=str(tmp_path))
    assert result['state'] in {'OK', 'NO_RESULTS', 'UNSUPPORTED', 'UNKNOWN'}
    assert 'serena' not in json.dumps(result).lower()
    module._close_services()


def test_graphify_ast_metadata_is_preserved():
    data = graph_data({'nodes': [{'id': 'f', 'label': 'parse', 'file_type': 'code', 'source_file': 'parser.py', 'source_location': 'L12-L19'}], 'edges': []})
    assert data['nodes'][0]['kind'] == 'code'
    assert data['nodes'][0]['line'] == 'L12-L19'
    assert data['nodes'][0]['path'] == 'parser.py'
