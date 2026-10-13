# KlapContext

**Understand an unfamiliar codebase before changing it.**

KlapContext convierte evidencia de código en un modelo del sistema: puntos de
entrada, flujos, automatizaciones, integraciones y sus incertidumbres.
Graphify puede funcionar como proveedor estándar de análisis técnico;
Serena puede sumar navegación semántica on demand por MCP; KlapContext conserva
analizadores locales y transforma toda evidencia mediante contratos
desacoplados para personas y agentes de IA.

## Agent Intelligence

KlapContext planifica el **mínimo contexto relevante** antes de que un agente
empiece a cambiar código. Según la intención —entender, modificar, depurar,
probar, refactorizar o medir impacto— selecciona capacidades y proveedores
necesarios, sin acoplarse a una herramienta externa ni cargar archivos enteros
por defecto. La compilación de Task Context llegará en los siguientes sprints.

KlapContext convierte un repositorio en contexto de ingeniería reutilizable: un
portal estático para personas y un briefing compacto para agentes de IA. Puede
usar [Graphify](https://github.com/Graphify-Labs/graphify) como motor local de
grafo, pero `klap init` sigue funcionando con proveedores nativos si no está.

```text
Repositorio → KlapContext → Contexto de ingeniería
                              ├── Portal humano
                              └── Contexto para agentes
```

## Instalación

```bash
pip install klapcontext
```

La instalación base no incorpora proveedores en el intérprete de KlapContext.
El primer `klap init` los prepara en entornos aislados bajo
`.klap/provider-runtime/`.

## Primer uso

```bash
cd mi-proyecto
klap init
klap open
```

`klap init` ejecuta los proveedores disponibles, escribe artefactos locales
bajo `.klap/` y prepara un `AGENTS.md` privado para que los agentes descubran el
contexto progresivamente. Ambos se agregan a `.git/info/exclude`; KlapContext
nunca modifica tu `.gitignore`.

`klap init` prepara Graphify y Serena con versiones fijadas si no encuentra una
instalación compatible. Si una preparación falla, los analizadores nativos
siguen generando contexto y el resumen registra el motivo. Graphify ejecuta una extracción real y usa
`.klap/graphify-out/graph.json` en `context.json`, el portal y la configuración
MCP. Si no está instalado o falla, los analizadores nativos siguen generando un
contexto útil y el reporte queda `PARTIAL`, con proveedores detectados,
ejecutados y omitidos (incluido el motivo). `context.json.analysis` conserva la
cobertura, trazas y contribuciones combinadas con procedencia. Se puede
deshabilitar Graphify explícitamente con
`.klap/providers.json` y `{"providers":{"graphify":{"enabled":false}}}`.

[Serena](https://github.com/oraios/serena) se integra de forma independiente y
intercambiable. Si falta una instalación compatible, Serena 1.7.0 se prepara
en el runtime local; KlapContext descubre sus
tools reales por MCP y ofrece símbolos, definiciones, referencias,
implementaciones e impacto por consulta. Durante `klap init` sólo ejecuta una
comprobación acotada de overview sobre un archivo elegible para verificar MCP;
no realiza búsquedas semánticas amplias, y nunca llama sus tools de escritura, shell,
onboarding o memorias. Ver [instalación, configuración, seguridad,
compatibilidad y límites](docs/SERENA.md).

Para compartir las instrucciones de onboarding con el equipo:

```bash
klap init --shared
```

El modo compartido genera un `AGENTS.md` versionable, sin rutas personales ni
secretos. Si el archivo ya existe, KlapContext preserva su contenido y sólo
administra el bloque entre `KLAPCONTEXT:START` y `KLAPCONTEXT:END`. Un archivo
versionado nunca se modifica silenciosamente en modo privado.

El portal incluye un árbol navegable de archivos y símbolos extraídos del grafo,
recorridos de llamadas y cambios recientes de Git. El contexto del agente y
`klap context` usan las mismas rutas y símbolos. El indicador de cobertura cuenta
archivos de código con al menos un nodo en Graphify: **no mide exhaustividad de
funciones ni garantiza que se hayan resuelto rutas dinámicas**. Los recorridos
son caminos del grafo, no afirmaciones de que una ruta HTTP los ejecuta; sus
ramas pueden requerir inspección del código original.

Antes de invocar Graphify, KlapContext calcula un **Index Scope** central desde
Git, manifests y reglas por stack. Excluye dependencias, caches, builds,
minificados y recursos binarios, pero permite excepciones locales en
`.klap/scope.json`. Revisalo con:

```bash
klap scope
klap scope --json
```

## Comandos

| Comando | Descripción |
| --- | --- |
| `klap init [ruta]` | Genera el contexto inicial. |
| `klap init --no-serena [ruta]` | Omite instalación, conexión y uso de Serena en esta ejecución. |
| `klap init --no-graphify [ruta]` | Omite instalación y ejecución de Graphify en esta ejecución. |
| `klap update [ruta]` | Reutiliza proveedores compatibles y actualiza el contexto. |
| `klap status [ruta]` | Indica si el contexto está actualizado respecto a Git. |
| `klap open [ruta]` | Abre el portal humano estático. |
| `klap agent [ruta]` | Muestra la configuración MCP local de Graphify. |
| `klap context "tarea" [ruta]` | Compila un contexto focalizado reutilizando `.klap/context.json` si existe. |
| `klap doctor --agent [ruta]` | Comprueba AGENTS.md, freshness, Graphify y configuración MCP. |
| `klap doctor --agent --repair [ruta]` | Repara proveedores estándar en runtimes locales. |
| `klap scope [ruta]` | Explica archivos incluidos/excluidos y sus motivos. |
| `klap migrate-graph [ruta]` | Planea la migración de grafos legacy; `--apply` preserva respaldos. |
| `klap --version` | Muestra la versión instalada. |

## Salidas

```text
.klap/
├── context.json          # modelo técnico, de sistema y humano
├── agent-context.md      # briefing para agentes de IA
├── index.html            # portal humano, sin servidor
├── state.json            # metadatos de freshness
├── mcp/                  # configuración local Graphify, cuando está disponible
└── graphify-out/         # grafo/informe opcionales de Graphify
```

`klap agent` genera ejemplos locales para Codex, Claude Code, Cursor y clientes
MCP genéricos. No instala agentes ni modifica configuraciones globales. Usá
`klap doctor --agent --probe-mcp` realiza un handshake MCP real, descubre tools
y ejecuta una consulta mínima `graph_stats`; falla si alguna etapa no se puede
comprobar.

El servidor MCP propio de KlapContext expone además búsquedas de símbolos,
definiciones, referencias, implementaciones, dependencias, impacto y
flujos/endpoints. Así, un cliente sólo necesita conectarse a KlapContext; el
adapter mantiene una sesión Serena reutilizable cuando está disponible. El
portal HTML sigue siendo estático y muestra únicamente datos precompilados: no
simula consultas semánticas dinámicas.

Las afirmaciones incluyen evidencia y confianza. Las consultas de proveedores
distinguen `OK`, `NO_RESULTS`, `UNSUPPORTED`, `PROVIDER_ERROR` y `UNKNOWN`; si
KlapContext no puede determinar algo, lo expone en lugar de inventarlo. Ver
[arquitectura y guía de adapters](docs/PROVIDERS.md).

## Desarrollo

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

## Publicación

El workflow de GitHub Actions publica tags `v*` mediante PyPI Trusted
Publishing. Antes del primer tag, configurá el publisher de PyPI para este
repositorio y workflow. No se necesitan tokens de PyPI en el repositorio.

El repositorio ya incluye `.github/workflows/publish-pypi.yml`: al publicar un
tag `vX.Y.Z`, GitHub construye el paquete y lo publica con ese publisher.

## Licencia

Apache-2.0. Ver [LICENSE](LICENSE).
