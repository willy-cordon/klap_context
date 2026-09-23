from __future__ import annotations
from pathlib import Path

def items(values, key="name"):
    return "\n".join(f"- {value.get(key) or value.get('path')}" for value in values) if values else "Sin evidencia disponible."
def render(context: dict) -> str:
    s=context.get("system_model",{}); purpose=s.get("purpose",{}).get("text") or "No fue posible determinar el propósito con confianza."
    sections=[("Propósito del Proyecto",purpose),("Cómo Funciona el Sistema",s.get("project_story",{}).get("text") or "No fue posible determinarlo con confianza."),("Superficies de Ejecución","\n".join(f"- {x['label']}: {x['count']}" for x in s.get("runtime_surfaces",[])) or "Sin superficies específicas detectadas."),("Rutas",items(s.get("routes",[]))),("Procesos Programados",items(s.get("scheduled_processes",[]))),("Jobs de Cola",items(s.get("queue_jobs",[]))),("Flujos Principales","\n".join(f"- **{x['name']}**: " + " → ".join(step["name"] for step in x["steps"]) for x in s.get("main_flows",[])) or "No se detectaron flujos principales con confianza."),("Dependencias Importantes","\n".join(f"- {x['package']} {x['version']} ({x['scope']})" for x in s.get("dependencies",[])[:12]) or "Sin dependencias específicas detectadas."),("Sistemas Externos",items(s.get("external_systems",[]))),("Almacenes de Datos",items(s.get("datastores",[]))),("Por Dónde Empezar","\n".join(f"- **{x['intent']}**: {', '.join(x['paths'])}" for x in s.get("start_here",[])) or "Sin recomendaciones detectadas."),("Incertidumbres","\n".join(f"- {x}" for x in s.get("unknowns",[])) or "Sin incertidumbres relevantes registradas.")]
    lines=["# KlapContext — Contexto del Proyecto"]
    for title,body in sections: lines.extend(["",f"## {title}",body])
    lines.extend(["","## Instrucciones para el Agente","1. Lee este contexto antes de explorar ampliamente el repositorio.","2. Usa Graphify MCP para dependencias y rutas de llamadas.","3. Consulta paths o vecinos relevantes antes de abrir muchos archivos.","4. Lee el código real antes de modificarlo.","5. Trata el contexto inferido como guía, no como verdad absoluta."])
    text="\n".join(lines)+"\n"; return text+f"\nTokens estimados: {len(text.split()) * 4 // 3}\n"
def write(context: dict, output: Path) -> str:
    text=render(context); output.write_text(text,encoding="utf-8"); return text
