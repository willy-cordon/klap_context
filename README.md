# KlapContext

**Understand an unfamiliar codebase before changing it.**

KlapContext convierte evidencia de código en un modelo del sistema: puntos de
entrada, flujos, automatizaciones, integraciones y sus incertidumbres.
Graphify funciona como proveedor de análisis técnico; KlapContext es la capa
que transforma esa evidencia en comprensión para personas y agentes de IA.

## Agent Intelligence

KlapContext planifica el **mínimo contexto relevante** antes de que un agente
empiece a cambiar código. Según la intención —entender, modificar, depurar,
probar, refactorizar o medir impacto— selecciona capacidades y proveedores
necesarios, sin acoplarse a una herramienta externa ni cargar archivos enteros
por defecto. La compilación de Task Context llegará en los siguientes sprints.

KlapContext convierte un repositorio en contexto de ingeniería reutilizable: un
portal estático para personas y un briefing compacto para agentes de IA. Usa
[Graphify](https://github.com/Graphify-Labs/graphify) como motor local de
análisis técnico; KlapContext no reimplementa su grafo ni sus parsers.

```text
Repositorio → KlapContext → Contexto de ingeniería
                              ├── Portal humano
                              └── Contexto para agentes
```

## Instalación

```bash
pip install klapcontext
```

La instalación incluye `graphifyy`, la distribución oficial de Graphify que
KlapContext necesita para generar el análisis local. Como alternativa para una
CLI aislada: `pipx install klapcontext`.

## Primer uso

```bash
cd mi-proyecto
klap init
klap open
```

`klap init` genera el análisis Graphify, escribe artefactos locales bajo
`.klap/` y prepara un `AGENTS.md` privado para que los agentes descubran el
contexto progresivamente. Ambos se agregan a `.git/info/exclude`; KlapContext
nunca modifica tu `.gitignore`.

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

## Comandos

| Comando | Descripción |
| --- | --- |
| `klap init [ruta]` | Genera el contexto inicial. |
| `klap update [ruta]` | Actualiza Graphify y el contexto. |
| `klap status [ruta]` | Indica si el contexto está actualizado respecto a Git. |
| `klap open [ruta]` | Abre el portal humano estático. |
| `klap agent [ruta]` | Muestra la configuración MCP local de Graphify. |
| `klap context "tarea" [ruta]` | Compila un contexto focalizado reutilizando `.klap/context.json` si existe. |
| `klap doctor --agent [ruta]` | Comprueba AGENTS.md, freshness, Graphify y configuración MCP. |
| `klap --version` | Muestra la versión instalada. |

## Salidas

```text
.klap/
├── context.json          # modelo técnico, de sistema y humano
├── agent-context.md      # briefing para agentes de IA
├── index.html            # portal humano, sin servidor
├── state.json            # metadatos de freshness
├── mcp/                  # configuración local reutilizable para clientes MCP
└── graphify/             # grafo, informe y visualizaciones de Graphify
```

`klap agent` genera ejemplos locales para Codex, Claude Code, Cursor y clientes
MCP genéricos. No instala agentes ni modifica configuraciones globales. Usá
`klap doctor --agent --probe-mcp` para comprobar que Graphify MCP puede iniciar;
eso no equivale a verificar una conexión real de un cliente.

Las afirmaciones incluyen evidencia y estados `CONFIRMED`, `INFERRED` o
`UNKNOWN`. Si KlapContext no puede determinar algo con confianza, lo expone en
lugar de inventarlo.

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
