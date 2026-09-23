from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .detector import detect_project
from .evidence import Evidence
from .git import commit
from .system import deployment, documents, entry_points, external_systems, purpose


def _nodes(graph: dict) -> list[dict]:
    return graph.get("nodes", []) if isinstance(graph.get("nodes"), list) else graph.get("graph", {}).get("nodes", [])


def _modules(nodes: list[dict]) -> list[dict]:
    result=[]
    for node in nodes:
        name=node.get("label") or node.get("name") or node.get("id"); path=node.get("file") or node.get("path")
        if name and path:
            kind=node.get("type", "module")
            result.append({"name":name,"path":path,"kind":kind,"description":f"Contains {str(kind).lower()} code related to {name}.","status":"CONFIRMED","evidence":[Evidence("graphify",str(path),"Graphify node", "CONFIRMED",1.0).as_dict()]})
    return result[:100]


def _runtime(points: list[dict], background: list[dict], framework: list[str]) -> dict:
    modes=[]; sentences=[]
    if any(p["type"] == "http" for p in points): modes.append("http"); sentences.append("Las solicitudes HTTP ingresan a través de declaraciones de rutas detectadas.")
    if any(p["type"] == "cli" for p in points): modes.append("cli"); sentences.append("El repositorio expone puntos de entrada ejecutables por línea de comandos.")
    if background: modes.append("scheduler"); sentences.append("La aplicación declara procesos programados en segundo plano.")
    if framework: sentences.append(f"La capa de framework detectada es {', '.join(framework)}.")
    return {"modes":modes,"layers":[],"description":" ".join(sentences) if sentences else None,"status":"CONFIRMED" if sentences else "UNKNOWN"}


def _io(points: list[dict], systems: list[dict], stores: list[dict]) -> tuple[list[dict], list[dict]]:
    inputs=[]; outputs=[]
    if any(p["type"]=="http" for p in points): inputs.append({"type":"http_request","description":"Solicitudes HTTP","status":"CONFIRMED"}) ; outputs.append({"type":"http_response","description":"Respuestas HTTP","status":"INFERRED"})
    if any(p["type"]=="cli" for p in points): inputs.append({"type":"cli","description":"Invocación por línea de comandos","status":"CONFIRMED"})
    if stores: inputs.append({"type":"datastore","description":"Lecturas o escrituras de base de datos","status":"INFERRED"}); outputs.append({"type":"datastore","description":"Escrituras de base de datos","status":"INFERRED"})
    for system in systems:
        if system["type"] == "http_api":
            outputs.append({"type":"external_api","description":system["name"],"status":"CONFIRMED"})
    return inputs, outputs


def _flows(points: list[dict], modules: list[dict], systems: list[dict], stores: list[dict]) -> list[dict]:
    flows=[]; targets=[m for m in modules if any(x in str(m["kind"]).lower() for x in ("controller","command","service"))]
    for point in points:
        if point["type"] not in {"http","scheduled"}: continue
        steps=[{"name":point["name"],"kind":"trigger","path":point.get("path")}]
        if point.get("target"): steps.append({"name":point["target"],"kind":"target","path":point.get("path")})
        for module in targets[:2]:
            if module["name"] != point.get("target"): steps.append({"name":module["name"],"kind":module["kind"],"path":module["path"]})
        if stores: steps.append({"name":stores[0]["name"],"kind":"datastore","path":None})
        elif systems: steps.append({"name":systems[0]["name"],"kind":"external_system","path":None})
        if len(steps) > 1:
            flows.append({"name":point["name"],"trigger":point["type"],"entry_point":point["name"],"steps":steps,"inputs":[],"outputs":[],"external_systems":[x["name"] for x in systems],"datastores":[x["name"] for x in stores],"tests":[],"status":"INFERRED","confidence":None,"evidence":point["evidence"]})
    return flows[:3]


def _important(root: Path, points: list[dict], deploy: dict, docs: list[dict]) -> list[dict]:
    result=[]
    for filename, role in (("pyproject.toml","Manifiesto de dependencias"),("package.json","Manifiesto de dependencias"),("composer.json","Manifiesto de dependencias"),("Dockerfile","Build de contenedor"),("docker-compose.yml","Topología de contenedores"),("README.md","Documentación del proyecto")):
        if (root/filename).exists(): result.append({"path":filename,"role":role,"reason":f"{role} detected"})
    for point in points:
        if point["path"] not in {x["path"] for x in result}: result.append({"path":point["path"],"role":f"{point['type']} entry points","reason":"Contains detected entry point"})
    return result[:20]


def _start_here(points: list[dict], background: list[dict], modules: list[dict], systems: list[dict], important: list[dict]) -> list[dict]:
    result=[]
    http=[p for p in points if p["type"]=="http"]
    if http: result.append({"intent":"Entender la API HTTP","paths":sorted({p["path"] for p in http}),"reason":"Contiene puntos de entrada HTTP confirmados"})
    if background: result.append({"intent":"Entender procesos en segundo plano","paths":sorted({p["path"] for p in background}),"reason":"Contiene procesos programados"})
    if systems: result.append({"intent":"Entender integraciones","paths":sorted({p for s in systems for p in s["configuration"]}),"reason":"Contiene configuración o uso de sistemas externos"})
    manifests=[x["path"] for x in important if x["role"]=="Dependency manifest"]
    if manifests: result.append({"intent":"Entender la configuración del proyecto","paths":manifests,"reason":"Manifiestos de dependencias"})
    return result


def _story(purpose_value: dict, runtime: dict, systems: list[dict], stores: list[dict], deploy: dict) -> dict:
    sentences=[]
    if purpose_value["text"]: sentences.append(purpose_value["text"].rstrip("." ) + ".")
    if runtime["description"]: sentences.append(runtime["description"])
    if systems: sentences.append("Los sistemas externos detectados incluyen " + ", ".join(x["name"] for x in systems) + ".")
    if stores: sentences.append("Los almacenes de datos detectados incluyen " + ", ".join(x["name"] for x in stores) + ".")
    if "Docker" in deploy["tools"]: sentences.append("La aplicación está contenerizada con Docker.")
    return {"text":" ".join(sentences) if sentences else None,"status":"CONFIRMED" if sentences else "UNKNOWN"}


def build(root: Path, graph: dict) -> dict:
    stack, stack_evidence=detect_project(root); docs=documents(root); purpose_value=purpose(root, docs)
    points, background=entry_points(root); systems, stores=external_systems(root); deploy, observability, _=deployment(root)
    modules=_modules(_nodes(graph)); runtime=_runtime(points, background, stack["frameworks"]); inputs, outputs=_io(points, systems, stores)
    flows=_flows(points, modules, systems, stores); important=_important(root, points, deploy, docs); start=_start_here(points, background, modules, systems, important)
    architecture={"style":None,"status":"UNKNOWN","confidence":None,"evidence":[]}
    if "Laravel" in stack["frameworks"]: architecture={"style":"MVC","status":"INFERRED","confidence":None,"evidence":[Evidence("file","composer.json","Laravel convention suggests MVC","INFERRED",.8).as_dict()]}
    tests=[{"path":path,"reason":"Test configuration or directory detected"} for path in ("tests","test","phpunit.xml","pytest.ini") if (root/path).exists()]
    name=root.name
    technical={"languages":stack["languages"],"frameworks":stack["frameworks"],"dependencies":[],"graph":{"nodes":len(_nodes(graph)),"edges":len(graph.get("edges", graph.get("graph",{}).get("edges",[])))},"documents":[{"path":d["path"]} for d in docs],"tests":tests,"infrastructure":stack["infrastructure"]}
    system={"purpose":purpose_value,"project_story":_story(purpose_value,runtime,systems,stores,deploy),"runtime":runtime,"entry_points":points,"main_flows":flows,"capabilities":modules,"inputs":inputs,"outputs":outputs,"external_systems":systems,"background_processes":background,"datastores":stores,"deployment":deploy,"observability":observability,"important_files":important,"start_here":start,"unknowns":[label for label,value in (("Propósito de negocio del proyecto",purpose_value["text"]),("Modelo de ejecución",runtime["description"]),("Plataforma de despliegue en producción",deploy["tools"])) if not value]}
    project={"name":name,"type":stack["frameworks"][0] if stack["frameworks"] else None,"root":str(root.resolve()),"generated_at":datetime.now(timezone.utc).isoformat(),"git_commit":commit(root)}
    # Keep v0.1 top-level fields for consumers while promoting the separated model.
    return {"schema_version":"0.2","project":project,"technical_model":technical,"system_model":system,"human_context":{"purpose":None,"users":None,"important_processes":[],"notes":[]},"stack":stack,"architecture":architecture,"entry_points":points,"modules":modules,"flows":flows,"api":[],"jobs":background,"datastores":stores,"external_systems":systems,"deployment":deploy,"observability":observability,"tests":tests,"evidence":[x.as_dict() for x in stack_evidence]+purpose_value["evidence"]}
