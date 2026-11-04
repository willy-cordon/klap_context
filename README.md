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

El menú contiene únicamente **Inicio** y **Git**. Inicio muestra el nombre real
del proyecto y un lienzo de grafo a pantalla completa, sin tarjetas de métricas.

- Rueda: zoom. Arrastre del fondo: desplazamiento. Arrastre de nodo: posición.
- Selección: nombre, tipo, archivo/línea cuando existen y relaciones resaltadas.
- Buscar: archivos o símbolos de todo el grafo, incluso fuera de la vista actual.
- Conexiones: enfocar los vecinos reales del nodo seleccionado.
- Ajustar y Ver todo: reencuadrar o volver a la vista inicial.
- Git: historial de cambios reciente, como en la versión anterior.

El HTML incluye los datos y el mismo motor de visualización que Graphify
(vis-network 9.1.6, licencia MIT), sin CDN, servidor ni solicitudes de red.
Podés abrir `.klap/index.html` directamente con `file://` o copiar ese único
archivo a otra máquina. No se agregan relaciones para mejorar el diseño.

En grafos grandes, la vista inicial muestra como máximo 350 nodos ordenados por
grado y lo indica como vista parcial. La búsqueda sigue cubriendo todos los
nodos; el enfoque muestra hasta 349 vecinos. Las conexiones dibujadas son
exclusivamente las del grafo original cuyos extremos están visibles. No es un
trazado de ejecución ni garantiza resolver llamadas dinámicas.

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
