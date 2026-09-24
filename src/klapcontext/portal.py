from __future__ import annotations

import html
import json
from pathlib import Path


def e(value: object) -> str:
    return html.escape(str(value))


def empty(message: str) -> str:
    return f"<p class='empty'>{e(message)}</p>"


def item_rows(items: list[dict], key: str = "name") -> str:
    if not items:
        return empty("Sin evidencia suficiente todavía.")
    return "".join(
        "<li><span class='dot'></span><div><strong>"
        f"{e(item.get(key) or item.get('path') or item.get('intent') or 'Sin nombre')}</strong>"
        f"<small>{e(item.get('type') or item.get('role') or item.get('description') or '')}</small>"
        "</div></li>"
        for item in items
    )


def system_map(interactions: dict) -> str:
    """Render a compact, intentionally abstract map for the dashboard overview."""
    nodes = interactions.get("nodes", [])[:9]
    edges = interactions.get("edges", [])[:14]
    if not nodes:
        return "<div class='map-empty'>El mapa aparecerá cuando haya interacciones verificables.</div>"

    positions = [(105, 92), (270, 50), (270, 142), (270, 234), (460, 92), (460, 190), (620, 140), (105, 220), (620, 260)]
    points = {node["name"]: positions[index] for index, node in enumerate(nodes)}
    links = "".join(
        f"<path d='M {points[edge['source']][0]} {points[edge['source']][1]} "
        f"C {points[edge['source']][0] + 70} {points[edge['source']][1]}, "
        f"{points[edge['target']][0] - 70} {points[edge['target']][1]}, "
        f"{points[edge['target']][0]} {points[edge['target']][1]}'/>"
        for edge in edges
        if edge.get("source") in points and edge.get("target") in points
    )
    boxes = "".join(
        f"<g class='map-node'><rect x='{points[node['name']][0] - 65}' y='{points[node['name']][1] - 24}' width='130' height='48' rx='8'/>"
        f"<text x='{points[node['name']][0]}' y='{points[node['name']][1] - 2}'>{e(node['name'])[:18]}</text>"
        f"<text class='map-kind' x='{points[node['name']][0]}' y='{points[node['name']][1] + 13}'>{e(node.get('type', 'componente'))[:18]}</text></g>"
        for node in nodes
    )
    return (
        "<div class='map-shell'><div class='map-legend'><span><i></i> interacción detectada</span>"
        "<span>vista conceptual</span></div><svg class='system-map' viewBox='0 0 720 300' role='img' "
        "aria-label='Mapa conceptual del sistema'><g class='map-links'>"
        f"{links}</g>{boxes}</svg></div>"
    )


def section(title: str, content: str, view: str, icon: str) -> str:
    return f"<section class='view' data-view='{view}' aria-label='{e(title)}'><div class='view-title'><span>{icon}</span><div><h2>{e(title)}</h2><p>Información extraída del repositorio y respaldada por evidencia.</p></div></div>{content}</section>"


def render(context: dict, agent_text: str, graphify_files: list[str]) -> str:
    project = context["project"]
    system = context.get("system_model", {})
    stack = [item for values in context.get("stack", {}).values() for item in values]
    points = system.get("entry_points", [])
    flows = system.get("main_flows", [])
    evidence = context.get("evidence", [])
    surfaces = system.get("runtime_surfaces", [])
    unknowns = system.get("unknowns", [])
    framework = system.get("framework") or {}
    purpose = system.get("purpose", {}).get("text") or "No pudimos determinar el propósito con suficiente confianza."
    story = system.get("project_story", {}).get("text") or system.get("runtime", {}).get("description") or "Todavía no hay una narrativa técnica verificable."
    state = "ACTUAL" if project.get("git_commit") else "SIN COMMIT"
    tags = "".join(f"<span>{e(item)}</span>" for item in stack[:6])
    if framework.get("version"):
        tags += f"<span>{e(framework.get('name', 'Framework'))} {e(framework['version'])}</span>"
    if framework.get("php_version"):
        tags += f"<span>PHP {e(framework['php_version'])}</span>"
    tags = tags or "<span>Stack no identificado</span>"
    surface_cards = "".join(
        f"<article class='surface'><b>{e(item.get('count', 0))}</b><span>{e(item.get('label', 'superficies'))}</span></article>"
        for item in surfaces
    ) or "<article class='surface'><b>—</b><span>superficies detectadas</span></article>"
    flow_cards = "".join(
        f"<article class='flow-card'><b>{e(flow.get('name', 'Flujo detectado'))}</b><p>"
        f"{' <em>→</em> '.join(e(step.get('name', 'paso')) for step in flow.get('steps', []))}</p></article>"
        for flow in flows
    ) or empty("No se detectaron flujos principales con confianza.")
    evidence_rows = "".join(
        f"<li><span class='dot'></span><div><strong>{e(item.get('path', 'archivo'))}</strong>"
        f"<small>{e(item.get('reason', 'Evidencia detectada'))}</small></div><mark>{e(item.get('status', 'CONFIRMED'))}</mark></li>"
        for item in evidence
    ) or empty("No se registró evidencia aún.")
    graph_links = "".join(
        f"<a href='graphify/{name}' target='_blank' rel='noreferrer'>{label}<span>↗</span></a>"
        for name, label in (("graph.html", "Abrir grafo técnico"), ("callflow.html", "Abrir call flows"), ("GRAPH_REPORT.md", "Abrir informe técnico"))
        if name in graphify_files
    ) or empty("No hay artefactos de Graphify disponibles.")
    start_rows = "".join(
        f"<li><b>{e(item.get('intent', 'Revisar el sistema'))}</b><small>{e(' · '.join(item.get('paths', [])))}</small></li>"
        for item in system.get("start_here", [])
    ) or empty("No hay recomendaciones de onboarding todavía.")
    flow_options = "".join(f"<option value='{index}'>{e(flow.get('name', 'Flujo'))}</option>" for index, flow in enumerate(flows))
    traces = json.dumps([[step.get("name", "paso") for step in flow.get("steps", [])] for flow in flows]).replace("</", "<\\/")

    overview = f"""
      <section class='overview-head'>
        <div><span class='eyebrow'>PANORAMA DEL SISTEMA</span><h1>{e(project['name'])}</h1>
          <p>{e(purpose)}</p><div class='tags'>{tags}</div></div>
        <div class='overview-state'><span class='live'>● {state}</span><small>análisis basado en {len(evidence)} evidencias</small></div>
      </section>
      <section class='map-card' aria-label='Mapa de interacción del sistema'><header><div><span class='icon'>⌘</span><div><h2>Mapa del sistema</h2><p>Componentes, relaciones y puntos de entrada en una sola lectura.</p></div></div><button class='outline' data-go='tecnico'>Explorar evidencia <span>→</span></button></header>{system_map(system.get('system_interactions', {}))}</section>
      <section class='quick-grid'>
        <article><b>{len(points)}</b><span>Puntos de entrada</span><small>CLI, HTTP, archivos o scheduler</small></article>
        <article><b>{len(flows)}</b><span>Flujos principales</span><small>Procesos y secuencias detectadas</small></article>
        <article><b>{len(evidence)}</b><span>Hechos confirmados</span><small>Con respaldo en el código</small></article>
        <article class='attention'><b>{len(unknowns)}</b><span>Incertidumbres</span><small>Aspectos pendientes de validar</small></article>
      </section>
      <section class='dashboard-bottom'><div class='compact-panel'><header><h2>Cómo se ejecuta</h2><button class='text-button' data-go='entradas'>Ver entradas →</button></header><div class='surfaces'>{surface_cards}</div></div>
      <div class='compact-panel'><header><h2>Lectura recomendada</h2><button class='text-button' data-go='flujos'>Ver flujos →</button></header><ul class='start-list'>{start_rows}</ul></div></section>
    """
    views = [
        section("Sistema", overview, "sistema", "⌘"),
        section("Flujos principales", f"<div class='flow-grid'>{flow_cards}</div>" + (f"<div class='trace-box'><label for='flow-select'>TRAZAR UN FLUJO</label><select id='flow-select'>{flow_options}</select><div id='flow-trace'></div></div>" if flows else ""), "flujos", "⌁"),
        section("Entradas", f"<div class='detail-grid'><article class='detail-card'><h3>Puntos de entrada</h3><ul class='detail-list'>{item_rows(points, 'intent')}</ul></article><article class='detail-card'><h3>Entradas y salidas</h3><div class='columns'><div><label>ENTRADAS</label><ul class='detail-list'>{item_rows(system.get('inputs', []), 'description')}</ul></div><div><label>SALIDAS</label><ul class='detail-list'>{item_rows(system.get('outputs', []), 'description')}</ul></div></div></article></div>", "entradas", "⇢"),
        section("Evidencia", f"<article class='detail-card evidence-card'><h3>Hechos que sostienen el mapa</h3><ul class='detail-list evidence-list'>{evidence_rows}</ul></article><article class='detail-card unknown-card'><h3>Lo que todavía no sabemos</h3><ul class='detail-list'>{item_rows([{'name': item, 'type': 'requiere validación'} for item in unknowns])}</ul></article>", "evidencia", "◈"),
        section("Exploración técnica", f"<div class='tech-hero'><h3>Profundizá en el análisis del código</h3><p>{e(story)}</p></div><div class='graph-links'>{graph_links}</div><div class='detail-grid'><article class='detail-card'><h3>Dependencias</h3><ul class='detail-list'>{item_rows(system.get('dependencies', []), 'package')}</ul></article><article class='detail-card'><h3>Procesos en segundo plano</h3><ul class='detail-list'>{item_rows(system.get('background_processes', []))}</ul></article></div>", "tecnico", "⌬"),
    ]
    agent = json.dumps(agent_text).replace("</", "<\\/")
    return f"""<!doctype html><html lang='es'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>KlapContext · {e(project['name'])}</title>
<style>
:root{{--bg:#07111f;--panel:#0c1a2d;--panel-2:#0e2036;--line:#1b3650;--ink:#edf7ff;--muted:#92a7be;--cyan:#16e0c4;--blue:#3d9cff;--violet:#976dff;--amber:#ffb648}}*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;color:var(--ink);font:14px/1.45 Inter,ui-sans-serif,system-ui,sans-serif;background:radial-gradient(900px 520px at 52% -130px,#153d5c70,transparent 70%),var(--bg)}}button,select{{font:inherit}}.top{{height:56px;display:flex;align-items:center;gap:14px;padding:0 18px;border-bottom:1px solid var(--line);background:#081422e8;backdrop-filter:blur(16px)}}.brand{{display:flex;align-items:center;gap:9px;font-weight:800;font-size:13px}}.logo{{display:grid;place-items:center;width:28px;height:28px;border-radius:7px;color:#051525;background:linear-gradient(135deg,var(--cyan),var(--violet));box-shadow:0 0 18px #16e0c455}}.top-title{{display:flex;flex-direction:column;border-left:1px solid var(--line);padding-left:14px}}.top-title b{{font-size:12px}}.top-title small{{color:var(--muted);font-size:10px}}.top-state{{margin-left:auto;color:var(--cyan);font:10px ui-monospace,monospace}}.repo{{padding:6px 9px;border:1px solid var(--line);border-radius:6px;color:#c5d8ed;font:10px ui-monospace,monospace}}.shell{{display:grid;grid-template-columns:174px minmax(0,1fr) 260px;min-height:calc(100vh - 56px)}}.side{{padding:14px 10px;border-right:1px solid var(--line);background:#081422aa}}.side button{{display:flex;width:100%;align-items:center;gap:9px;padding:10px;border:0;border-radius:6px;background:transparent;color:var(--muted);text-align:left;cursor:pointer;font-size:12px}}.side button:hover,.side button.active{{background:linear-gradient(90deg,#0c514d88,#0c243b);color:var(--ink);box-shadow:inset 2px 0 var(--cyan)}}.side .nav-icon{{color:var(--cyan);font-size:16px;width:19px;text-align:center}}.side-footer{{margin-top:28px;padding-top:16px;border-top:1px solid var(--line)}}main{{padding:16px;min-width:0;max-width:1220px;width:100%;margin:auto}}.view{{display:none;animation:in .28s ease}}.view.active{{display:block}}@keyframes in{{from{{opacity:.35;transform:translateY(6px)}}to{{opacity:1;transform:none}}}}.view-title{{display:none}}.overview-head{{display:flex;justify-content:space-between;gap:24px;padding:5px 4px 15px}}.eyebrow,label{{color:var(--cyan);font:10px ui-monospace,monospace;letter-spacing:.13em}}h1{{margin:3px 0 4px;font-size:25px;letter-spacing:-.045em}}h2,h3,p{{margin-top:0}}.overview-head p{{max-width:760px;margin-bottom:9px;color:#c6d7e7;font-size:12px}}.overview-state{{display:flex;align-items:flex-end;flex-direction:column;gap:5px;white-space:nowrap}}.live{{color:var(--cyan);font:10px ui-monospace,monospace}}.overview-state small{{color:var(--muted);font-size:10px}}.tags{{display:flex;gap:5px;flex-wrap:wrap}}.tags span{{padding:3px 6px;border:1px solid #29506b;border-radius:4px;color:#aac0d8;font:9px ui-monospace,monospace}}.map-card,.compact-panel,.detail-card,.flow-card,.trace-box{{border:1px solid var(--line);border-radius:9px;background:linear-gradient(135deg,#0d2037e8,#091727e8);box-shadow:0 18px 35px #00000018}}header{{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:13px 14px;border-bottom:1px solid #1a334c}}header>div{{display:flex;align-items:center;gap:9px}}header h2{{margin:0;font-size:13px}}header p{{margin:2px 0 0;color:var(--muted);font-size:10px}}.icon{{display:grid;place-items:center;width:28px;height:28px;border-radius:6px;color:var(--cyan);background:#0a3b4277;font-size:17px}}.outline,.text-button{{border:1px solid #24658a;border-radius:6px;background:#0a1a2d;color:var(--cyan);padding:7px 9px;font-size:10px;font-weight:700;cursor:pointer}}.text-button{{border:0;background:transparent;padding:0}}.map-shell{{padding:9px 12px 10px;background:radial-gradient(circle at 50% 42%,#123e5570,transparent 60%)}}.map-legend{{display:flex;justify-content:space-between;color:var(--muted);font:9px ui-monospace,monospace}}.map-legend i{{display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--cyan);margin-right:4px}}.system-map{{display:block;width:100%;height:min(33vh,280px)}}.map-links path{{fill:none;stroke:#22e2cf9c;stroke-width:1.5;filter:drop-shadow(0 0 3px #20e3d055)}}.map-node rect{{fill:#102b49;stroke:#2f83b4;stroke-width:1}}.map-node text{{fill:#e7f5ff;font:10px ui-monospace,monospace;text-anchor:middle}}.map-node .map-kind{{fill:#84a3bd;font-size:8px}}.map-empty{{padding:58px;text-align:center;color:var(--muted)}}.quick-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:9px;margin:10px 0}}.quick-grid article{{min-height:85px;padding:11px;border:1px solid var(--line);border-radius:7px;background:#0b192b}}.quick-grid b{{display:block;color:#f2f8ff;font-size:24px;letter-spacing:-.06em}}.quick-grid span{{display:block;font-size:10px;font-weight:700}}.quick-grid small{{display:block;margin-top:4px;color:var(--muted);font-size:9px}}.quick-grid .attention b{{color:var(--amber)}}.dashboard-bottom,.detail-grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}.compact-panel header{{padding:11px 13px}}.compact-panel h2{{font-size:12px}}.surfaces{{display:grid;grid-template-columns:repeat(4,1fr);gap:7px;padding:10px}}.surface{{padding:8px;border-radius:5px;background:#091628;border:1px solid #1c3a54}}.surface b{{display:block;color:var(--cyan);font-size:18px}}.surface span{{color:var(--muted);font-size:9px}}.start-list,.detail-list{{list-style:none;margin:0;padding:8px 13px}}.start-list li{{padding:5px 0;border-bottom:1px solid #1a324a}}.start-list li:last-child,.detail-list li:last-child{{border:0}}.start-list b,.detail-list strong{{display:block;font-size:11px}}.start-list small,.detail-list small{{display:block;color:var(--muted);font-size:9px}}.empty{{padding:8px 13px;color:var(--muted);font-size:11px}}.right{{padding:16px 11px;border-left:1px solid var(--line);background:#081422aa}}.agent-card,.insight-card{{padding:14px;margin-bottom:10px;border:1px solid var(--line);border-radius:8px;background:linear-gradient(145deg,#122a47,#0b182b)}}.agent-card{{border-color:#317b8d}}.agent-card h3,.insight-card h3{{margin-bottom:7px;font-size:12px}}.agent-card p,.insight-card p{{color:#b4c5d7;font-size:10px}}.copy{{width:100%;border:0;border-radius:5px;padding:9px;background:linear-gradient(90deg,var(--cyan),#46d1e7);color:#03202a;font-weight:800;cursor:pointer;font-size:11px}}.insight-card ul{{list-style:none;margin:0;padding:0}}.insight-card li{{padding:7px 0;border-bottom:1px solid #22405a;color:#c0d2e4;font-size:10px}}.insight-card li:last-child{{border:0}}.view-title{{margin:0 0 13px;align-items:center;gap:9px}}.view-title>span{{display:grid;place-items:center;width:31px;height:31px;border-radius:7px;background:#0a3b4277;color:var(--cyan);font-size:19px}}.view-title h2{{margin:0;font-size:18px}}.view-title p{{margin:2px 0 0;color:var(--muted);font-size:10px}}.flow-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}}.flow-card{{padding:15px}}.flow-card b{{font-size:13px}}.flow-card p{{margin:8px 0 0;color:#b9cce0;font:10px/1.8 ui-monospace,monospace}}em{{color:var(--cyan);font-style:normal}}.trace-box{{margin-top:10px;padding:14px}}select{{display:block;margin:7px 0;padding:8px;border:1px solid var(--line);border-radius:5px;background:#081727;color:var(--ink);font-size:11px}}#flow-trace{{color:var(--cyan);font:11px/1.7 ui-monospace,monospace}}.detail-card{{padding:15px}}.detail-card h3{{font-size:13px}}.detail-list{{padding:0}}.detail-list li{{display:flex;gap:8px;align-items:flex-start;padding:8px 0;border-bottom:1px solid #1a324a}}.dot{{display:block;flex:none;width:6px;height:6px;margin-top:5px;border-radius:50%;background:var(--violet);box-shadow:0 0 7px var(--violet)}}.evidence-list mark{{margin-left:auto;border-radius:3px;padding:2px 4px;background:#10493f;color:var(--cyan);font:8px ui-monospace,monospace}}.unknown-card{{margin-top:10px}}.columns{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}.tech-hero{{padding:19px;border:1px solid #2f4968;border-radius:9px;background:linear-gradient(120deg,#172d50,#10192f)}}.tech-hero h3{{margin-bottom:6px;font-size:16px}}.tech-hero p{{margin:0;color:#b4c7dc;font-size:12px}}.graph-links{{display:flex;gap:10px;margin:10px 0}}.graph-links a{{flex:1;padding:13px;border:1px solid #2c5875;border-radius:7px;background:#0b1a2d;color:#d9efff;text-decoration:none;font-size:11px;font-weight:700}}.graph-links a span{{float:right;color:var(--cyan)}}@media(max-width:1050px){{.shell{{grid-template-columns:160px minmax(0,1fr)}}.right{{display:none}}}}@media(max-width:720px){{.shell{{display:block}}.side{{display:flex;overflow:auto;padding:8px;border-bottom:1px solid var(--line)}}.side button{{min-width:max-content}}.side-footer{{display:none}}.top-title{{display:none}}.repo{{display:none}}main{{padding:10px}}.overview-head{{display:block}}.overview-state{{margin-top:10px;align-items:flex-start}}.quick-grid{{grid-template-columns:repeat(2,1fr)}}.dashboard-bottom,.detail-grid,.flow-grid,.columns{{grid-template-columns:1fr}}.system-map{{width:680px;max-width:none}}.map-shell{{overflow:auto}}.surfaces{{grid-template-columns:repeat(2,1fr)}}}}
</style></head><body><nav class='top'><div class='brand'><span class='logo'>K</span>klap_context</div><div class='top-title'><b>Comprender el sistema</b><small>Explorá componentes, flujos y evidencia de tu repositorio.</small></div><span class='top-state'>● {state}</span><span class='repo'>{e(project['name'])}</span></nav><div class='shell'><aside class='side'><button class='active' data-go='sistema'><span class='nav-icon'>⌘</span>Sistema</button><button data-go='flujos'><span class='nav-icon'>⌁</span>Flujos</button><button data-go='entradas'><span class='nav-icon'>⇢</span>Entradas</button><button data-go='evidencia'><span class='nav-icon'>◈</span>Evidencias</button><button data-go='tecnico'><span class='nav-icon'>⌬</span>Graphify</button><div class='side-footer'><button data-go='evidencia'><span class='nav-icon'>?</span>Ayuda y confianza</button></div></aside><main>{''.join(views)}</main><aside class='right'><section class='agent-card'><h3>✦ Acciones para agente</h3><p>Generá un briefing listo para usar y profundizá luego en el sistema.</p><button class='copy' onclick='copyContext(this)'>▣ Copiar contexto</button></section><section class='insight-card'><h3>💡 Hallazgos principales <span>{min(len(evidence), 9)}</span></h3><ul><li>{len(points)} punto(s) de entrada detectado(s).</li><li>{len(flows)} flujo(s) principal(es) disponible(s).</li><li>{len(evidence)} hecho(s) con respaldo en el código.</li></ul></section><section class='insight-card'><h3>⚡ Siguiente paso</h3><p>Usá las vistas laterales para investigar un área, sin perder el panorama inicial.</p></section></aside></div><script>const agentContext={agent};const views=[...document.querySelectorAll('.view')];const nav=[...document.querySelectorAll('[data-go]')];function go(name){{views.forEach(view=>view.classList.toggle('active',view.dataset.view===name));nav.forEach(button=>button.classList.toggle('active',button.dataset.go===name));history.replaceState(null,'','#'+name);window.scrollTo({{top:0,behavior:'smooth'}})}}nav.forEach(button=>button.addEventListener('click',()=>go(button.dataset.go)));go(location.hash.slice(1)||'sistema');function copyContext(button){{navigator.clipboard.writeText(agentContext).then(()=>{{const old=button.textContent;button.textContent='✓ Contexto copiado';setTimeout(()=>button.textContent=old,1500)}})}}const paths={traces};const selector=document.querySelector('#flow-select');if(selector){{const trace=document.querySelector('#flow-trace');const show=()=>trace.textContent=paths[selector.value].join(' → ');selector.addEventListener('change',show);show();}}</script></body></html>"""


def write(context: dict, agent_text: str, graphify_files: list[str], output: Path) -> None:
    output.write_text(render(context, agent_text, graphify_files), encoding="utf-8")
