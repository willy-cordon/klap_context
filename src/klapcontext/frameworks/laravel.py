"""Conservative Laravel conventions scanner; Graphify remains the code graph."""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..evidence import Evidence


def _read(path: Path) -> str:
    try: return path.read_text(encoding="utf-8", errors="replace")
    except OSError: return ""


def _e(path: str, reason: str, status: str="CONFIRMED") -> list[dict]:
    return [Evidence("file", path, reason, status, 1.0 if status == "CONFIRMED" else .8).as_dict()]


def _symbol(target: str) -> str | None:
    target=target.strip()
    match=re.search(r"(?:\[\s*)?([A-Za-z_][\w\\]+)::class\s*,\s*['\"](\w+)['\"]", target)
    return f"{match.group(1).split('\\')[-1]}::{match.group(2)}" if match else None


def analyze(root: Path) -> dict:
    routes=[]; commands=[]; scheduled=[]; jobs=[]; dependencies=[]; important=[]
    route_dir=root/"routes"
    if route_dir.is_dir():
        for file in route_dir.glob("*.php"):
            text=_read(file); rel=str(file.relative_to(root))
            for method, uri, target in re.findall(r"Route::(get|post|put|patch|delete|any)\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*(.+?)\);", text, re.S|re.I):
                routes.append({"type":"http","method":method.upper(),"uri":"/"+uri.lstrip("/"),"name":f"{method.upper()} /{uri.lstrip('/')}","target":_symbol(target),"middleware":[],"source":rel,"status":"CONFIRMED","evidence":_e(rel,"Declaración de ruta Laravel")})
            for resource, controller in re.findall(r"Route::(?:api)?resource\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*([A-Za-z_][\w\\]+)::class", text, re.I):
                routes.append({"type":"http","method":"RESOURCE","uri":"/"+resource.lstrip("/"),"name":f"RESOURCE /{resource.lstrip('/')}","target":controller.split("\\")[-1],"middleware":[],"source":rel,"status":"INFERRED","evidence":_e(rel,"Declaración resource de Laravel","INFERRED")})
            if file.name == "console.php":
                for command, freq in re.findall(r"Schedule::command\s*\(\s*['\"]([^'\"]+)['\"]\s*\).*?->([A-Za-z]\w*)\s*\(", text, re.S):
                    scheduled.append({"name":command,"type":"scheduled_command","schedule":freq,"path":rel,"status":"CONFIRMED","evidence":_e(rel,"Comando programado de Laravel")})
    commands_dir=root/"app"/"Console"/"Commands"
    if commands_dir.is_dir():
        for file in commands_dir.glob("*.php"):
            text=_read(file); signature=re.search(r"(?:protected|public)\s+\$signature\s*=\s*['\"]([^'\"]+)", text)
            commands.append({"name":signature.group(1) if signature else file.stem,"type":"artisan_command","path":str(file.relative_to(root)),"status":"CONFIRMED","evidence":_e(str(file.relative_to(root)),"Clase de comando Artisan")})
    jobs_dir=root/"app"/"Jobs"
    if jobs_dir.is_dir():
        for file in jobs_dir.glob("*.php"):
            text=_read(file); rel=str(file.relative_to(root))
            if "ShouldQueue" in text:
                queue=re.search(r"(?:public|protected)\s+\$queue\s*=\s*['\"]([^'\"]+)", text)
                jobs.append({"name":file.stem,"type":"queue_job","queue":queue.group(1) if queue else None,"path":rel,"status":"CONFIRMED","evidence":_e(rel,"Job Laravel que implementa ShouldQueue")})
    composer=root/"composer.json"
    if composer.exists():
        try:
            data=json.loads(_read(composer))
            for scope,key in (("runtime","require"),("development","require-dev")):
                for name, version in data.get(key,{}).items(): dependencies.append({"package":name,"version":version,"scope":scope,"category":_category(name),"status":"CONFIRMED","evidence":_e("composer.json",f"Dependencia Composer ({scope})")})
        except json.JSONDecodeError: pass
    for path,role in (("routes/api.php","Rutas HTTP API"),("routes/web.php","Rutas web"),("routes/console.php","Programación de comandos"),("app/Console/Kernel.php","Scheduler Laravel"),("config/database.php","Configuración de base de datos"),("bootstrap/app.php","Bootstrap de aplicación"),("composer.json","Dependencias PHP")):
        if (root/path).exists(): important.append({"path":path,"role":role,"reason":f"{role} detectado"})
    surfaces=[]
    if routes: surfaces.append({"type":"http","label":"HTTP","count":len(routes),"items":routes})
    if commands: surfaces.append({"type":"cli","label":"CLI","count":len(commands),"items":commands})
    if scheduled: surfaces.append({"type":"scheduler","label":"Scheduler","count":len(scheduled),"items":scheduled})
    if jobs: surfaces.append({"type":"queue","label":"Queue","count":len(jobs),"items":jobs})
    return {"routes":routes,"commands":commands,"scheduled_processes":scheduled,"queue_jobs":jobs,"dependencies":dependencies,"runtime_surfaces":surfaces,"important_files":important}


def _category(package: str) -> str:
    if package == "laravel/framework": return "framework"
    if "phpunit" in package or "pest" in package: return "testing"
    if "sentry" in package: return "observability"
    if "guzzle" in package: return "http"
    if "jwt" in package or "sanctum" in package: return "authentication"
    return "other"
