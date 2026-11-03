"""Graph-first local portal. Analysis facts remain in the agent artifacts."""
from __future__ import annotations

import html
import json
from pathlib import Path


def e(value: object) -> str:
    return html.escape(str(value), quote=True)


def graph_data(graph: dict) -> dict:
    """Project actual Graphify records without synthesizing nodes or relations."""
    from .context_builder import _nodes, _edges

    nodes, identifiers = [], set()
    for node in _nodes(graph):
        if not isinstance(node, dict) or node.get("id") is None:
            continue
        identifier = str(node["id"])
        if identifier in identifiers:
            continue
        identifiers.add(identifier)
        nodes.append({"id": identifier, "label": str(node.get("label") or node.get("name") or identifier),
                      "kind": str(node.get("type") or node.get("kind") or node.get("file_type") or "unknown"),
                      "path": str(node.get("source_file") or node.get("file") or node.get("path") or ""),
                      "line": node.get("line") or node.get("start_line") or node.get("source_location")})
    edges = []
    for edge in _edges(graph):
        if not isinstance(edge, dict):
            continue
        source, target = edge.get("source"), edge.get("target")
        source = source.get("id") if isinstance(source, dict) else source
        target = target.get("id") if isinstance(target, dict) else target
        if source is None or target is None or str(source) not in identifiers or str(target) not in identifiers:
            continue
        edges.append({"id": len(edges), "from": str(source), "to": str(target),
                      "relation": str(edge.get("relation") or edge.get("type") or edge.get("label") or "")})
    return {"nodes": nodes, "edges": edges}


CSS = """
:root{color-scheme:dark;--bg:#0b111b;--ink:#e8eff9;--muted:#8fa2bc;--line:#25334a;--accent:#71e5c1}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,sans-serif}
header{height:88px;padding:16px 28px;display:flex;align-items:center;gap:16px;border-bottom:1px solid var(--line)}
.mark{display:grid;place-items:center;width:38px;height:38px;border:1px solid var(--accent);border-radius:12px;color:var(--accent);font-weight:800;font-size:22px}
.identity small{color:var(--muted);font-size:11px;letter-spacing:.12em}.identity h1{font-size:21px;margin:0;max-width:55vw;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
nav{margin-left:auto;display:flex;gap:8px}a,button,input,select{font:inherit}nav a,button,select{border:1px solid var(--line);border-radius:9px;background:#141e2d;color:var(--ink);padding:8px 13px;text-decoration:none;cursor:pointer}
nav a[aria-current=page],button:hover{border-color:var(--accent);color:var(--accent)}:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
[hidden]{display:none!important}#inicio{height:calc(100dvh - 88px);min-height:460px;position:relative;background:radial-gradient(ellipse at 50% 40%,#14243a 0%,var(--bg) 70%)}
#graph{width:100%;height:100%;position:absolute;inset:0}.toolbar{position:absolute;z-index:2;top:20px;left:24px;right:24px;display:flex;gap:8px;flex-wrap:wrap;pointer-events:none}.toolbar>*{pointer-events:auto}
input{width:min(300px,65vw);padding:9px 13px;border:1px solid var(--line);border-radius:9px;background:#111d2eef;color:var(--ink)}
#results{position:absolute;top:48px;left:0;max-height:260px;overflow:auto;width:min(430px,90vw);background:#111d2e;border:1px solid var(--line);border-radius:9px}#results button{display:block;text-align:left;width:100%;border:0;border-radius:0;overflow-wrap:anywhere}
#selection{position:absolute;bottom:55px;left:24px;max-width:min(600px,90vw);padding:12px 16px;background:#111d2ef5;border:1px solid var(--line);border-radius:10px;overflow-wrap:anywhere}#selection strong,#selection span{display:block}#selection span{color:var(--muted)}
.footer{position:absolute;bottom:16px;left:24px;right:24px;display:flex;justify-content:space-between;gap:12px;color:var(--muted);font-size:11px;pointer-events:none}.legend{display:flex;gap:12px;flex-wrap:wrap}.legend i{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:4px}
.empty{position:absolute;inset:25% 12%;display:grid;align-content:center;text-align:center;color:var(--muted)}.empty h2{color:var(--ink);font-size:24px}.empty code{color:var(--accent)}
#historial{max-width:900px;padding:32px 24px;margin:auto}#historial h2{font-size:26px}#historial ul{list-style:none;padding:0}#historial li{padding:16px 0;border-bottom:1px solid var(--line)}#historial small{display:block;color:var(--muted)}
@media(max-width:600px){header{padding:12px;height:80px;gap:10px}.identity h1{font-size:17px;max-width:40vw}.mark{display:none}nav a{padding:7px 10px}#inicio{height:calc(100dvh - 80px)}.toolbar{left:12px;right:12px;top:12px}.footer{left:12px;right:12px;flex-direction:column;gap:4px}.hint{display:block}}
"""


def render(context: dict, agent_text: str, graphify_files: list[str], *, graph: dict | None = None) -> str:
    """Render supplied Graphify facts only; legacy arguments remain compatible."""
    project_name = context.get("project", {}).get("name") or "Proyecto sin nombre"
    data = graph_data(graph or {})
    recent = "".join(
        f"<li><strong>{e(row.get('subject', 'Cambio'))}</strong><small>{e(row.get('date', ''))} · {e(str(row.get('commit', ''))[:10])}</small></li>"
        for row in context.get("system_model", {}).get("recent_changes", [])
    ) or "<li>No hay historial disponible.</li>"
    if data["nodes"]:
        content = """<div id="graph" role="application" aria-label="Grafo interactivo de Graphify"></div>
<div class="toolbar"><input id="search" type="search" aria-label="Buscar archivo o símbolo" placeholder="Buscar archivo o símbolo…" autocomplete="off"><div id="results" hidden></div><button id="fit">Ajustar</button><button id="reset">Ver todo</button><button id="focus" disabled>Conexiones</button></div>
<div id="selection" aria-live="polite" hidden></div><div class="footer"><div id="legend" class="legend"></div><span id="hint" class="hint">Arrastrá para explorar · Rueda para zoom</span></div>"""
        library = Path(__file__).with_name("assets").joinpath("vis-network.min.js").read_text(encoding="utf-8")
        script = Path(__file__).with_name("assets").joinpath("portal.js").read_text(encoding="utf-8")
        payload = json.dumps(data, ensure_ascii=True).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
        scripts = f'<script>{library}</script><script id="graph-data" type="application/json">{payload}</script><script>{script}</script>'
    else:
        content = '<div class="empty"><h2>Grafo de Graphify no disponible</h2><p>El contexto de los analizadores nativos sigue disponible para agentes.</p><p>Ejecutá <code>klap update</code> con Graphify disponible para generar el grafo.</p></div>'
        scripts = ""
    navigation = """<script>
function showPage(){const git=location.hash==='#historial';document.querySelector('#inicio').hidden=git;document.querySelector('#historial').hidden=!git;document.querySelectorAll('nav a').forEach(a=>{if(a.hash===(git?'#historial':'#inicio'))a.setAttribute('aria-current','page');else a.removeAttribute('aria-current')});if(!git)window.dispatchEvent(new Event('resize'))}
window.addEventListener('hashchange',showPage);showPage();
</script>"""
    return f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(project_name)} · KlapContext</title><style>{CSS}</style></head><body>
<header><span class="mark" aria-hidden="true">K</span><div class="identity"><small>KlapContext</small><h1>{e(project_name)}</h1></div><nav aria-label="Navegación principal"><a href="#inicio" aria-current="page">Inicio</a><a href="#historial">Git</a></nav></header>
<main><section id="inicio" aria-label="Explorar proyecto">{content}</section><section id="historial" hidden><h2>Historial Git</h2><ul>{recent}</ul></section></main>{scripts}{navigation}</body></html>'''


def write(context: dict, agent_text: str, graphify_files: list[str], output: Path, *, graph: dict | None = None) -> None:
    output.write_text(render(context, agent_text, graphify_files, graph=graph), encoding="utf-8")
