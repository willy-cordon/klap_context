# KlapContext

**El grafo es el producto.**

Abrí un repositorio y explorá su arquitectura: nombre del proyecto → grafo
interactivo → conexiones. [Graphify](https://github.com/Graphify-Labs/graphify)
genera los nodos y relaciones; KlapContext conserva contexto técnico verificable
para agentes y analizadores nativos complementarios.

## Instalación y primer uso

```bash
pip install klapcontext
cd mi-proyecto
klap init
klap open
```

El primer `init` prepara Graphify 0.9.102 en un entorno aislado bajo
`.klap/provider-runtime/` si no existe una instalación compatible. No modifica
el Python global ni PATH. Una falla de instalación o extracción se informa;
los analizadores nativos siguen generando contexto, sin presentar su salida
como un grafo de Graphify.

```bash
klap update             # actualiza contexto y grafo
klap status             # comprueba vigencia
klap init --no-graphify # sólo contexto nativo, sin instalación externa
klap doctor --agent     # diagnóstico
```

También podés deshabilitar Graphify persistentemente en `.klap/providers.json`:

```json
{"providers":{"graphify":{"enabled":false}}}
```

## Portal local

`.klap/index.html` distribuye el visualizador nativo de Graphify: comunidades
coloreadas, búsqueda, selección e inspección de nodos. Es el mismo mapa que
`.klap/graphify-out/graph.html`, con `vis-network 9.1.6` embebido para abrirlo
sin CDN ni servidor con `file://`.

La vista humana omite nodos externos sin archivo fuente (por ejemplo símbolos
no resueltos de dependencias); el grafo canónico completo se preserva para MCP
y análisis técnico. No se agregan relaciones ni se infiere una ejecución.

## Contexto para agentes

La simplificación visual no elimina entradas, flujos, evidencias ni alcance del
índice de los artefactos técnicos:

```text
.klap/
├── index.html            # portal autónomo: Inicio + Git
├── context.json          # contexto estructurado, evidencia y relaciones
├── agent-context.md      # briefing progresivo
├── graphify-out/         # graph.json y exportaciones originales de Graphify
├── provider-runtime/     # entorno aislado de Graphify
├── provider-state.json   # estado del runtime
├── state.json            # snapshot y vigencia
├── scope.json            # reglas de alcance
└── mcp/                  # ejemplos de conexión Graphify MCP
```

`AGENTS.md` se genera con un bloque administrado, preservando contenido ajeno.
Por defecto los artefactos privados se agregan a `.git/info/exclude`, nunca a
`.gitignore`. Un `AGENTS.md` versionado requiere autorización para actualizarlo.
Para compartirlo: `klap init --shared`.

```bash
klap scope
klap context "modificar autenticación" --json
klap agent
klap doctor --agent --probe-mcp
```

Se conserva el servidor MCP propio (`mcp_server.py`) y sus consultas de contexto,
símbolos, definiciones, referencias, implementaciones, dependencias, impacto y
flujos. Cada capacidad depende de los analizadores disponibles: devuelve
`UNSUPPORTED`, `UNKNOWN` o errores explícitos cuando no puede resolverla, sin
simular capacidades semánticas. No requiere ningún servidor semántico externo.
Los ejemplos `.klap/mcp/` siguen destinados a Graphify; no modifican configuraciones
globales de agentes.

Ver [arquitectura](docs/ARCHITECTURE.md), [proveedores](docs/PROVIDERS.md) y
[migración graph-first](docs/GRAPH_FIRST.md).

## Desarrollo

```bash
python -m pip install -e ".[dev]"
python -m pytest
python -m build
```

La suite de navegador es opcional: `pip install playwright`, luego
`python -m playwright install chromium` y `python -m pytest tests/test_portal_browser.py`.
Usa HTML local y bloquea la red para comprobar que el portal es autónomo.

## Licencia

Apache-2.0. Ver [LICENSE](LICENSE). El renderizador distribuido conserva su
[licencia MIT](src/klapcontext/assets/vis-network.LICENSE).
