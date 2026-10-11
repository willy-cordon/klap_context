"""Offline, evidence-backed HTML portal."""
from __future__ import annotations

import html
import json
from pathlib import Path


def e(value: object) -> str:
    return html.escape(str(value))


def empty(message: str) -> str:
    return f"<p class='empty'>{e(message)}</p>"


def items(rows: list[dict], key: str = "name") -> str:
    if not rows:
        return empty("Sin evidencia suficiente todavía.")
    return "".join(
        f"<li><i></i><div><b>{e(row.get(key) or row.get('name') or row.get('path') or row.get('intent') or 'Sin nombre')}</b><small>{e(row.get('type') or row.get('role') or row.get('reason') or row.get('description') or '')}</small></div></li>"
        for row in rows
    )


def map_html(interactions: dict) -> str:
    nodes = interactions.get("nodes", [])[:8]
    if not nodes:
        return "<p class='map-empty'>El mapa aparecerá cuando haya interacciones verificables.</p>"
    positions = [(75, 75), (220, 42), (220, 130), (220, 214), (400, 75), (400, 174), (565, 130), (75, 208)]
    names = [node.get("name", f"node-{index}") for index, node in enumerate(nodes)]
    points = dict(zip(names, positions))
    edges = "".join(
        f"<path d='M {points[edge['source']][0]} {points[edge['source']][1]} C {points[edge['source']][0]+55} {points[edge['source']][1]}, {points[edge['target']][0]-55} {points[edge['target']][1]}, {points[edge['target']][0]} {points[edge['target']][1]}'/>"
        for edge in interactions.get("edges", [])[:14]
        if edge.get("source") in points and edge.get("target") in points
    )
    boxes = "".join(
        f"<g class='node' tabindex='0' role='link' data-evidence-link><rect x='{points[name][0]-50}' y='{points[name][1]-18}' width='100' height='36' rx='6'/><text x='{points[name][0]}' y='{points[name][1]-1}'>{e(node.get('name', 'componente'))[:14]}</text><text class='kind' x='{points[name][0]}' y='{points[name][1]+11}'>{e(node.get('type', 'componente'))[:14]}</text></g>"
        for name, node in zip(names, nodes)
    )
    return f"<div class='map'><svg viewBox='0 0 640 260' role='img' aria-label='Mapa de relaciones; cada componente lleva a las evidencias'><g class='edges'>{edges}</g>{boxes}</svg></div>"


def view(title: str, name: str, body: str, icon: str) -> str:
    return f"<section class='view' id='{name}' aria-labelledby='{name}-title'><header class='view-head'><span aria-hidden='true'>{icon}</span><div><h2 id='{name}-title'>{e(title)}</h2><p>Datos extraídos del repositorio y respaldados por evidencia.</p></div></header>{body}</section>"


def tree(files: list[dict]) -> str:
    if not files:
        return empty("No se encontraron archivos.")
    rows = []
    for file in files:
        symbols = "".join(f"<li>{e(x.get('name', 'símbolo'))} <small>{e(x.get('kind', ''))}</small></li>" for x in file.get("symbols", [])[:100])
        rows.append(f"<details class='source-file'><summary>{e(file.get('path', 'archivo'))} <small>{len(file.get('symbols', []))} símbolos</small></summary><ul>{symbols or '<li>Sin símbolos detectados.</li>'}</ul></details>")
    return "".join(rows)


CSS = """
:root{--bg:#101820;--surface:#1B2630;--up:#263440;--cyan:#00E5F0;--cyan2:#40F5FF;--ink:#F3F6F8;--muted:#AAB9C5;--line:#354650;--ok:#39DFA6;--warn:#FFBF69;--bad:#FF657A}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;min-width:320px;color:var(--ink);font:15px/1.5 Inter,ui-sans-serif,system-ui,sans-serif;background:var(--bg);background-image:linear-gradient(#fff2 1px,transparent 1px),linear-gradient(90deg,#fff2 1px,transparent 1px);background-size:28px 28px}button,input,select{font:inherit}button,a,summary{cursor:pointer}button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible{outline:3px solid var(--cyan);outline-offset:3px}.portal{max-width:1400px;margin:auto;padding:16px}.frame{overflow:hidden;border:1px solid var(--line);border-radius:17px;background:#111c24e8;box-shadow:0 22px 65px #0009}.mast{display:flex;align-items:center;gap:12px;padding:12px 20px;border-bottom:1px solid var(--line)}.mark{display:grid;place-items:center;width:35px;height:35px;border-radius:9px;background:#d4dde1;color:#101820;font-size:22px;font-weight:900}.mast b{font-size:14px}.mast small,.view-head p,small,.empty{display:block;color:var(--muted);font-size:11px}.state{margin-left:auto;color:var(--ok);font:11px ui-monospace,monospace}.nav{position:sticky;top:0;z-index:10;display:flex;gap:7px;overflow-x:auto;padding:12px 20px;border-bottom:1px solid var(--line);background:#111c24f5}.nav a{flex:none;border:1px solid var(--line);border-radius:7px;padding:6px 11px;background:#14212a;color:var(--ink);font-size:11px;font-weight:800;text-decoration:none}.nav a:hover,.nav a.active{border-color:var(--cyan);background:var(--cyan);color:#071217}.hero{display:grid;grid-template-columns:minmax(0,1fr) minmax(370px,.95fr);gap:28px;padding:28px;border-bottom:1px solid var(--line)}.eyebrow{color:var(--cyan);font:700 10px ui-monospace,monospace;letter-spacing:.16em}.identity h1{margin:7px 0 10px;font-family:Impact,Haettenschweiler,'Arial Narrow Bold',sans-serif;font-size:clamp(42px,7vw,76px);line-height:.85;letter-spacing:.04em;overflow-wrap:anywhere;text-shadow:3px 3px var(--cyan)}.identity p{max-width:450px;font-size:16px;font-weight:650}.tags{display:flex;flex-wrap:wrap;gap:7px}.tags span{padding:3px 8px;border:1px solid var(--cyan);border-radius:5px;font:10px ui-monospace,monospace}.copy{margin-top:18px;border:0;border-radius:7px;padding:12px 17px;background:var(--cyan);color:#071217;font-weight:950;letter-spacing:.04em;box-shadow:0 4px #008c96}.copy:hover{background:var(--cyan2)}.intro{color:var(--muted);font-size:12px!important;font-weight:400!important}.checks{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin:18px 0 0;padding:14px 0 0;border-top:2px solid var(--ink)}.checks li{list-style:none;color:var(--muted);font-size:10px}.console-wrap{position:relative;padding-top:25px}.label{position:absolute;z-index:2;top:0;left:50%;transform:translateX(-50%);min-width:180px;border:4px solid #38505c;border-radius:8px 8px 0 0;padding:5px 10px;background:var(--cyan);color:#061519;text-align:center;font:900 10px ui-monospace,monospace}.console{border:4px solid #596872;border-radius:25px;padding:21px 22px 28px;background:linear-gradient(135deg,#80909a,#3d4a52 55%,#667680);box-shadow:inset 2px 2px #aeb9be,inset -4px -5px #263038,0 16px 30px #0008}.screen{min-height:310px;border:8px solid #121b20;border-radius:13px;padding:13px;background:#061d26;box-shadow:inset 0 0 0 2px #274552,inset 0 0 24px #00e5f033;color:var(--cyan)}.screen-top{display:flex;justify-content:space-between;gap:8px;border-bottom:1px solid var(--cyan);padding-bottom:6px;font:800 10px ui-monospace,monospace}.screen h2{font:900 14px ui-monospace,monospace}.map{min-height:130px;overflow:auto;border:1px dashed #00e5f099}.map svg{display:block;min-width:440px;width:100%;height:130px}.edges path{fill:none;stroke:#00e5f0aa;stroke-width:1.5}.node{cursor:pointer}.node rect{fill:#0b3542;stroke:var(--cyan)}.node text{fill:var(--ink);font:10px ui-monospace,monospace;text-anchor:middle}.node .kind{fill:#9eeff3;font-size:8px}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:4px;margin-top:9px;padding-top:8px;border-top:1px solid #00e5f066}.stats b{display:block;font:900 19px ui-monospace,monospace}.stats span{font-size:8px;color:#b0eef2}.note{font:9px/1.35 ui-monospace,monospace}.controls{display:grid;grid-template-columns:1fr 72px;gap:14px;align-items:center;margin-top:15px}.mini{display:flex;gap:8px;justify-content:center}.mini button,.mini a{border:1px solid #1c3f49;border-radius:999px;padding:5px 9px;background:#17323c;color:var(--cyan);font:900 8px ui-monospace,monospace;text-decoration:none}.buttons{display:flex;justify-content:space-between}.buttons button,.buttons a{display:grid;place-items:center;width:32px;height:32px;border:2px solid #087b84;border-radius:50%;background:var(--cyan);color:#071217;font-weight:950;box-shadow:0 3px #075960;text-decoration:none}.view{scroll-margin-top:60px;padding:32px 28px;border-bottom:1px solid var(--line)}.view-head{display:flex;gap:9px;align-items:center;margin-bottom:16px}.view-head>span{display:grid;place-items:center;width:31px;height:31px;border:1px solid var(--cyan);border-radius:6px;color:var(--cyan)}.view-head h2{margin:0;font-size:20px}.view-head p{margin:1px 0}.grid,.two,.columns{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.card,.flow,.trace,.tech{padding:16px;border:1px solid var(--line);border-radius:9px;background:var(--surface)}.list{margin:0;padding:0;list-style:none}.list li{display:flex;gap:8px;padding:9px 0;border-bottom:1px solid var(--line)}.list li:last-child{border:0}.list i{flex:none;width:7px;height:7px;margin-top:7px;border-radius:50%;background:var(--cyan)}.evidence mark{margin-left:auto;height:max-content;background:#16453a;color:var(--ok);font-size:9px}.unknown{margin-top:12px}.links{display:flex;flex-wrap:wrap;gap:9px;margin:12px 0}.links a{flex:1;border:1px solid var(--cyan);border-radius:6px;padding:9px;background:#122b35;color:var(--cyan);font-weight:800;text-decoration:none}.files{max-height:70vh;overflow:auto;margin-top:12px;padding:14px;border:1px solid var(--line);border-radius:9px;background:var(--surface)}.files details{padding:5px;border-bottom:1px solid var(--line)}.files summary{cursor:pointer}.files ul{padding-left:20px}#search,select{width:100%;padding:10px;border:1px solid var(--line);border-radius:6px;background:var(--surface);color:var(--ink)}#trace{margin-top:10px;color:var(--cyan);font-family:ui-monospace,monospace}.help{max-width:440px;border:1px solid var(--cyan);border-radius:10px;background:var(--up);color:var(--ink);box-shadow:0 20px 60px #000b}.help::backdrop{background:#000b}.help button{float:right;border:0;border-radius:5px;padding:6px 9px;background:var(--cyan);color:#071217;font-weight:800}@media(max-width:900px){.hero{grid-template-columns:1fr;max-width:680px;margin:auto}.console-wrap{order:-1}}@media(max-width:620px){.portal{padding:0}.frame{border-radius:0;border-left:0;border-right:0}.mast{padding:10px 13px}.mast small{display:none}.nav{padding:9px 12px}.hero,.view{padding:20px 14px}.identity h1{font-size:51px}.console{padding:17px 13px 24px}.screen{padding:10px}.grid,.two,.columns,.checks{grid-template-columns:1fr}}
"""


def render(context: dict, agent_text: str, graphify_files: list[str]) -> str:
    project, system = context["project"], context.get("system_model", {})
    stack = [item for values in context.get("stack", {}).values() if isinstance(values, list) for item in values]
    points, flows, evidence = system.get("entry_points", []), system.get("main_flows", []), context.get("evidence", [])
    unknowns, scope, explore = system.get("unknowns", []), system.get("index_scope", {}), system.get("exploration", {})
    framework = system.get("framework") or {}
    state = context.get("freshness", {}).get("status") or ("CURRENT" if project.get("git_commit") else "UNINITIALIZED")
    project_name = project.get("name") or "Proyecto sin nombre"
    tags = "".join(f"<span>{e(x)}</span>" for x in stack[:6]) or "<span>Stack no identificado</span>"
    if framework.get("version"):
        tags += f"<span>{e(framework.get('name', 'Framework'))} {e(framework['version'])}</span>"
    if framework.get("php_version"):
        tags += f"<span>PHP {e(framework['php_version'])}</span>"
    purpose = system.get("purpose", {}).get("text") or "No pudimos determinar el propósito con suficiente confianza."
    flow_cards = "".join(f"<article class='flow'><b>{e(flow.get('name', 'Flujo detectado'))}</b><p>{' <em>→</em> '.join(e(step.get('name', 'paso')) for step in flow.get('steps', []))}</p></article>" for flow in flows) or empty("No se detectaron flujos principales con confianza.")
    evidence_rows = "".join(f"<li><i></i><div><b>{e(x.get('path', 'archivo'))}</b><small>{e(x.get('reason', 'Evidencia detectada'))}</small></div><mark>{e(x.get('status', 'CONFIRMED'))}</mark></li>" for x in evidence) or empty("No se registró evidencia aún.")
    options = "".join(f"<option value='{i}'>{e(x.get('name', 'Flujo'))}</option>" for i, x in enumerate(flows))
    traces = json.dumps([[step.get("name", "paso") for step in x.get("steps", [])] for x in flows]).replace("</", "<\\/")
    graph_links = "".join(f"<a href='graphify-out/{name}' target='_blank' rel='noreferrer'>{label} ↗</a>" for name, label in [("graph.html", "Abrir grafo técnico"), ("GRAPH_REPORT.md", "Abrir informe técnico")] if name in graphify_files) or empty("No hay artefactos de Graphify disponibles.")
    providers = [{"name": x.get("name"), "description": f"{x.get('status', 'UNKNOWN')} · {'ejecutado' if x.get('executed') else x.get('reason', 'no ejecutado')}"} for x in context.get("analysis", {}).get("providers", [])]
    roots = [{"name": x.get("path"), "description": f"{x.get('files', 0)} archivos incluidos"} for x in scope.get("included_roots", [])]
    excluded = [{"name": x, "description": f"{n} archivos"} for x, n in scope.get("excluded_reasons", {}).items()]
    call_cards = "".join(f"<article class='flow'><b>{e(x.get('name', 'Recorrido'))}</b><p>{' <em>→</em> '.join(e(s.get('name', 'paso')) for s in x.get('steps', []))}</p></article>" for x in explore.get("call_paths", [])) or empty("No hay recorridos de llamadas verificables en el grafo.")
    recent = "".join(f"<li><i></i><div><b>{e(x.get('subject', 'Cambio'))}</b><small>{e(x.get('date', ''))} · {e(x.get('commit', '')[:10])}</small></div></li>" for x in system.get("recent_changes", [])) or empty("No hay historial disponible.")
    views = [
        view("Sistema", "sistema", f"<div class='tech'><h3>Resumen de {e(project_name)}</h3><p>{e(system.get('project_story', {}).get('text') or purpose)}</p></div>", "⌘"),
        view("Flujos principales", "flujos", f"<div class='grid'>{flow_cards}</div>" + (f"<div class='trace'><label for='flow-select'>TRAZAR UN FLUJO</label><select id='flow-select'>{options}</select><div id='trace'></div></div>" if flows else ""), "⌁"),
        view("Entradas", "entradas", f"<div class='two'><article class='card'><h3>Puntos de entrada</h3><ul class='list'>{items(points, 'intent')}</ul></article><article class='card'><h3>Entradas y salidas</h3><div class='columns'><div><label>ENTRADAS</label><ul class='list'>{items(system.get('inputs', []), 'description')}</ul></div><div><label>SALIDAS</label><ul class='list'>{items(system.get('outputs', []), 'description')}</ul></div></div></article></div>", "⇢"),
        view("Evidencias", "evidencia", f"<article class='card'><h3>Hechos que sostienen el mapa</h3><ul class='list evidence'>{evidence_rows}</ul></article><article class='card unknown'><h3>Lo que todavía no sabemos</h3><ul class='list'>{items([{'name': x, 'type': 'requiere validación'} for x in unknowns])}</ul></article>", "◈"),
        view("Index Scope", "scope", f"<div class='tech'><h3>Qué entró al índice</h3><p>{scope.get('included_code_files', 0)} archivos de código incluidos; {scope.get('excluded_files', 0)} recursos excluidos; {scope.get('graph_nodes_outside_scope', 0)} nodos fuera del alcance. Configuración: <code>.klap/scope.json</code>.</p></div><div class='two'><article class='card'><h3>Directorios incluidos</h3><ul class='list'>{items(roots)}</ul></article><article class='card'><h3>Exclusiones por motivo</h3><ul class='list'>{items(excluded)}</ul></article></div>", "◎"),
        view("Archivos y símbolos", "archivos", f"<input id='search' type='search' placeholder='Buscar archivo o símbolo' aria-label='Buscar archivo o símbolo'><div class='files'>{tree(explore.get('files', []))}</div>", "▤"),
        view("Recorridos del grafo", "recorridos", f"<p class='empty'>Estas rutas muestran llamadas conectadas en Graphify; no implican todas las ramas.</p><div class='grid'>{call_cards}</div>", "⌁"),
        view("Historial Git", "historial", f"<article class='card'><h3>Cambios recientes</h3><ul class='list'>{recent}</ul></article>", "◷"),
        view("Graphify y proveedores", "tecnico", f"<div class='tech'><h3>Profundizá en el análisis del código</h3><p>{e(system.get('project_story', {}).get('text') or 'Todavía no hay una narrativa técnica verificable.')}</p></div><div class='links'>{graph_links}</div><div class='two'><article class='card'><h3>Dependencias</h3><ul class='list'>{items(system.get('dependencies', []), 'package')}</ul></article><article class='card'><h3>Proveedores precompilados</h3><ul class='list'>{items(providers)}</ul></article></div>", "⌬"),
    ]
    onboarding = context.get("agent_onboarding", {})
    checks = "".join(["<li>Reporte generado desde evidencia local</li>", f"<li>{'✓' if onboarding.get('status') in {'configured', 'unchanged'} else '○'} AGENTS.md</li>", "<li>✓ Contexto en .klap/</li>", f"<li>{'✓' if graphify_files else '○'} Graphify</li>", f"<li>{'✓' if onboarding.get('mcp', {}).get('available', False) else '○'} MCP</li>"])
    console = f"<div class='console-wrap'><div class='label'>ANÁLISIS LOCAL<br><small>{len(evidence)} evidencias</small></div><section class='console' aria-label='Consola de análisis de {e(project_name)}'><div class='screen'><div class='screen-top'><span>{e(project_name)}</span><span>{e(state)}</span></div><h2>Mapa del sistema</h2>{map_html(system.get('system_interactions', {}))}<div class='stats'><div><span>Entradas</span><b>{len(points)}</b></div><div><span>Flujos</span><b>{len(flows)}</b></div><div><span>Confirmados</span><b>{len(evidence)}</b></div><div><span>Pendientes</span><b>{len(unknowns)}</b></div></div><p class='note'>Abrí una sección para profundizar en el análisis y su evidencia.</p></div><div class='controls'><div class='mini'><button data-help>Select · ayuda</button><a href='#sistema'>Start · explorar</a></div><div class='buttons'><button data-copy aria-label='Copiar contexto de agente'>A</button><a href='#evidencia' aria-label='Ir a evidencias'>B</a></div></div></section></div>"
    script = """<script>const ctx=__CTX__,paths=__PATHS__,help=document.querySelector('#help'),links=[...document.querySelectorAll('.nav a')],sections=[...document.querySelectorAll('.view')];document.querySelectorAll('[data-copy]').forEach(b=>b.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(ctx);const t=b.textContent;b.textContent='✓';setTimeout(()=>b.textContent=t,1500)}catch{b.textContent='!'}}));document.querySelectorAll('[data-help]').forEach(b=>b.addEventListener('click',()=>help.showModal()));document.querySelector('[data-close]').addEventListener('click',()=>help.close());document.querySelectorAll('[data-evidence-link]').forEach(n=>{const open=()=>document.querySelector('#evidencia').scrollIntoView({behavior:'smooth'});n.addEventListener('click',open);n.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();open()}})});const q=document.querySelector('#search');if(q)q.addEventListener('input',()=>document.querySelectorAll('.source-file').forEach(f=>f.hidden=!f.textContent.toLowerCase().includes(q.value.toLowerCase())));const s=document.querySelector('#flow-select');if(s){const out=document.querySelector('#trace'),show=()=>out.textContent=(paths[s.value]||[]).join(' → ');s.addEventListener('change',show);show()}const observer=new IntersectionObserver(rows=>rows.forEach(row=>{if(row.isIntersecting)links.forEach(link=>link.classList.toggle('active',link.getAttribute('href')==='#'+row.target.id))}),{rootMargin:'-25% 0px -65% 0px'});sections.forEach(section=>observer.observe(section));</script>""".replace("__CTX__", json.dumps(agent_text).replace("</", "<\\/")).replace("__PATHS__", traces)
    navigation = [("sistema", "Sistema"), ("flujos", "Flujos"), ("entradas", "Entradas"), ("evidencia", "Evidencias"), ("scope", "Index Scope"), ("archivos", "Archivos"), ("recorridos", "Recorridos"), ("historial", "Git"), ("tecnico", "Graphify")]
    top = "<nav class='nav' aria-label='Navegación del reporte'>" + "".join(f"<a href='#{key}'>{label}</a>" for key, label in navigation) + "</nav>"
    return f"<!doctype html><html lang='es'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{e(project_name)} · KlapContext</title><style>{CSS}</style></head><body><div class='portal'><div class='frame'><header class='mast'><span class='mark'>K</span><div><b>KlapContext</b><small>Reporte de ingeniería del repositorio</small></div><span class='state'>● {e(state)}</span></header>{top}<section class='hero' aria-labelledby='project-title'><div class='identity'><span class='eyebrow'>REPORTE DE INGENIERÍA</span><h1 id='project-title'>{e(project_name)}</h1><p>{e(purpose)}</p><div class='tags'>{tags}</div><button class='copy' data-copy>COPIAR CONTEXTO →</button><p class='intro'>Briefing listo para usar con un agente y navegar la evidencia técnica del proyecto.</p><ul class='checks'>{checks}</ul></div>{console}</section>{''.join(views)}</div></div><dialog class='help' id='help'><div><button data-close>Cerrar</button><h2>Confianza y navegación</h2><p>Los hechos confirmados se extraen durante <code>klap init</code>. Cada sección conserva los datos precompilados y su trazabilidad; las ausencias se muestran explícitamente.</p></div></dialog>{script}</body></html>"


def write(context: dict, agent_text: str, graphify_files: list[str], output: Path) -> None:
    output.write_text(render(context, agent_text, graphify_files), encoding="utf-8")
