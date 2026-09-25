# Agent Onboarding

`klap init` prepara un punto de entrada compacto para agentes compatibles con
`AGENTS.md`. El bloque administrado referencia el conocimiento en `.klap/`; no
duplica el briefing ni el grafo.

## Seguridad de AGENTS.md

- Los marcadores `KLAPCONTEXT:START` y `KLAPCONTEXT:END` delimitan la única
  sección que KlapContext puede actualizar.
- Marcadores incompletos, invertidos o duplicados producen un conflicto y no
  se escribe el archivo.
- Las escrituras son atómicas y el contenido previo se respalda localmente en
  `.klap/backups/AGENTS.md`.
- En modo privado, un `AGENTS.md` nuevo se agrega a `.git/info/exclude`.
- Un `AGENTS.md` versionado exige autorización interactiva o
  `--allow-tracked-agents`; `--shared` es autorización explícita para generar
  instrucciones versionables.

## MCP

KlapContext genera archivos locales en `.klap/mcp/` para Graphify MCP. No
modifica configuraciones globales ni almacena credenciales. Los ejemplos cubren
configuración JSON genérica —utilizable por Claude Code y Cursor al copiarla
explícitamente— y un snippet TOML para Codex.

## Diagnóstico

```bash
klap doctor --agent
klap doctor --agent --probe-mcp
```

El diagnóstico distingue configuración generada, capacidad de iniciar el
servidor y conexión real de un cliente. La última nunca se afirma sólo por la
existencia de un archivo.
