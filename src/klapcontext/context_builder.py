from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from .detector import detect_project
from .evidence import Evidence
from .frameworks.laravel import analyze as analyze_laravel
from .git import commit
from .system import deployment, documents, entry_points, external_systems, purpose

def _nodes(graph): return graph.get("nodes",[]) if isinstance(graph.get("nodes"),list) else graph.get("graph",{}).get("nodes",[])
def _modules(nodes):
    return [{"name":n.get("label") or n.get("name") or n.get("id"),"path":n.get("file") or n.get("path"),"kind":n.get("type","module"),"description":None,"status":"CONFIRMED","evidence":[]} for n in nodes if (n.get("label") or n.get("name") or n.get("id")) and (n.get("file") or n.get("path"))][:100]
def _runtime(points, background, framework):
    modes=[]; text=[]
    if any(p["type"]=="http" for p in points): modes.append("http"); text.append("Las solicitudes HTTP ingresan por las rutas detectadas.")
    if any(p["type"] in {"cli","artisan_command"} for p in points): modes.append("cli"); text.append("La aplicación expone comandos ejecutables.")
    if background: modes.append("scheduler"); text.append("La aplicación declara procesamiento en segundo plano.")
    return {"modes":modes,"layers":framework,"description":" ".join(text) or None,"status":"CONFIRMED" if text else "UNKNOWN"}
def _io(points, systems, stores):
    inputs=[]; outputs=[]
    if any(p["type"]=="http" for p in points): inputs.append({"type":"http_request","description":"Solicitudes HTTP","status":"CONFIRMED"}); outputs.append({"type":"http_response","description":"Respuestas HTTP","status":"INFERRED"})
    if any(p["type"] in {"cli","artisan_command"} for p in points): inputs.append({"type":"cli","description":"Invocación por línea de comandos","status":"CONFIRMED"})
    if stores: inputs.append({"type":"datastore","description":"Base de datos","status":"INFERRED"}); outputs.append({"type":"datastore","description":"Escrituras de base de datos","status":"INFERRED"})
    return inputs,outputs
def _flows(root, laravel, stores, systems):
    flows=[]
    for route in laravel["routes"][:8]:
        steps=[{"name":route["name"],"kind":"route","path":route["source"]}]
        if route.get("target"):
            steps.append({"name":route["target"],"kind":"controller","path":route["source"]})
            ctrl=root/"app"/"Http"/"Controllers"/(route["target"].split("::")[0]+".php")
            if ctrl.exists():
                import re
                names=re.findall(r"\b(\w*(?:Service|Repository))\b",ctrl.read_text(encoding="utf-8",errors="replace"))
                if names: steps.append({"name":names[0],"kind":"service","path":None})
        if stores: steps.append({"name":stores[0]["name"],"kind":"datastore","path":None})
        elif systems: steps.append({"name":systems[0]["name"],"kind":"external_system","path":None})
        if len(steps)>1: flows.append({"name":route["name"],"trigger":"http","entry_point":route["name"],"steps":steps,"status":"INFERRED","confidence":None,"evidence":route["evidence"],"inputs":[],"outputs":[],"external_systems":[],"datastores":[],"tests":[]})
    for command in laravel["scheduled_processes"][:3]: flows.append({"name":command["name"],"trigger":"scheduler","entry_point":command["name"],"steps":[{"name":"Scheduler","kind":"scheduler","path":command["path"]},{"name":command["name"],"kind":"command","path":command["path"]}],"status":"CONFIRMED","confidence":None,"evidence":command["evidence"],"inputs":[],"outputs":[],"external_systems":[],"datastores":[],"tests":[]})
    return flows[:10]
def _interactions(flows, systems, stores):
    nodes=[]; edges=[]
    def n(name,kind):
        if not any(x["name"]==name for x in nodes): nodes.append({"name":name,"type":kind})
    for flow in flows:
        previous=None
        for step in flow["steps"]:
            n(step["name"],step["kind"])
            if previous: edges.append({"source":previous,"target":step["name"],"label":"uses" if step["kind"] in {"datastore","external_system"} else "calls"})
            previous=step["name"]
    for x in stores: n(x["name"],"datastore")
    for x in systems: n(x["name"],"external_system")
    return {"nodes":nodes[:30],"edges":edges[:45],"status":"INFERRED" if edges else "UNKNOWN"}
def _start(root, laravel, systems):
    result=[]
    for path,intent in (("routes/api.php","Entender la API"),("routes/web.php","Entender las rutas web"),("routes/console.php","Entender procesamiento programado"),("composer.json","Entender dependencias"),("config/database.php","Entender acceso a datos")):
        if (root/path).exists(): result.append({"intent":intent,"paths":[path],"reason":"Archivo Laravel relevante detectado"})
    if systems: result.append({"intent":"Entender integraciones","paths":sorted({p for s in systems for p in s["configuration"]}),"reason":"Sistemas externos detectados"})
    return result
def build(root: Path, graph: dict) -> dict:
    stack,evidence=detect_project(root); docs=documents(root); value=purpose(root,docs); systems,stores=external_systems(root); deploy,observability,_=deployment(root)
    laravel=analyze_laravel(root) if "Laravel" in stack["frameworks"] else {"routes":[],"commands":[],"scheduled_processes":[],"queue_jobs":[],"dependencies":[],"runtime_surfaces":[],"important_files":[]}
    generic_points,generic_background=entry_points(root)
    points=laravel["routes"]+laravel["commands"] or generic_points; background=laravel["scheduled_processes"]+laravel["queue_jobs"] or generic_background
    runtime=_runtime(points,background,stack["frameworks"]); inputs,outputs=_io(points,systems,stores); flows=_flows(root,laravel,stores,systems) if laravel["routes"] else []
    important=laravel["important_files"] or [{"path":"README.md","role":"Documentación","reason":"README detectado"}] if (root/"README.md").exists() else []
    tests=[{"path":x,"reason":"Tests detectados"} for x in ("tests","test","phpunit.xml","pytest.ini") if (root/x).exists()]
    story=" ".join(x for x in [value["text"],runtime["description"],("La aplicación está contenerizada con Docker." if "Docker" in deploy["tools"] else None)] if x)
    system={"purpose":value,"project_story":{"text":story or None,"status":"CONFIRMED" if story else "UNKNOWN"},"runtime":runtime,"runtime_surfaces":laravel["runtime_surfaces"],"routes":laravel["routes"],"commands":laravel["commands"],"scheduled_processes":laravel["scheduled_processes"],"queue_jobs":laravel["queue_jobs"],"dependencies":laravel["dependencies"],"entry_points":points,"main_flows":flows,"system_interactions":_interactions(flows,systems,stores),"capabilities":_modules(_nodes(graph)),"inputs":inputs,"outputs":outputs,"external_systems":systems,"background_processes":background,"datastores":stores,"deployment":deploy,"observability":observability,"important_files":important,"start_here":_start(root,laravel,systems),"unknowns":[x for x,ok in (("Propósito de negocio del proyecto",value["text"]),("Plataforma de despliegue en producción",deploy["tools"])) if not ok]}
    technical={"languages":stack["languages"],"frameworks":stack["frameworks"],"dependencies":laravel["dependencies"],"graph":{"nodes":len(_nodes(graph)),"edges":len(graph.get("edges",graph.get("graph",{}).get("edges",[])))},"documents":[{"path":d["path"]} for d in docs],"tests":tests,"infrastructure":stack["infrastructure"]}
    project={"name":root.name,"type":stack["frameworks"][0] if stack["frameworks"] else None,"root":str(root.resolve()),"generated_at":datetime.now(timezone.utc).isoformat(),"git_commit":commit(root)}
    return {"schema_version":"0.3","project":project,"technical_model":technical,"system_model":system,"human_context":{"purpose":None,"users":None,"important_processes":[],"notes":[]},"stack":stack,"architecture":{"style":"MVC" if "Laravel" in stack["frameworks"] else None,"status":"INFERRED" if "Laravel" in stack["frameworks"] else "UNKNOWN","confidence":None,"evidence":[]},"entry_points":points,"modules":system["capabilities"],"flows":flows,"api":laravel["routes"],"jobs":background,"datastores":stores,"external_systems":systems,"deployment":deploy,"observability":observability,"tests":tests,"evidence":[x.as_dict() for x in evidence]+value["evidence"]}
