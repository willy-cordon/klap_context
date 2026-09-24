# KlapContext

**Understand an unfamiliar codebase before changing it.**

KlapContext convierte evidencia de código en un modelo del sistema: puntos de
entrada, flujos, automatizaciones, integraciones y sus incertidumbres.
Graphify funciona como proveedor de análisis técnico; KlapContext es la capa
que transforma esa evidencia en comprensión para personas y agentes de IA.

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

`klap init` genera el análisis Graphify y escribe artefactos locales bajo
`.klap/`. KlapContext agrega esa carpeta a `.git/info/exclude`; nunca modifica
tu `.gitignore`.

## Comandos

| Comando | Descripción |
| --- | --- |
| `klap init [ruta]` | Genera el contexto inicial. |
| `klap update [ruta]` | Actualiza Graphify y el contexto. |
| `klap status [ruta]` | Indica si el contexto está actualizado respecto a Git. |
| `klap open [ruta]` | Abre el portal humano estático. |
| `klap agent [ruta]` | Muestra la configuración MCP local de Graphify. |
| `klap --version` | Muestra la versión instalada. |

## Salidas

```text
.klap/
├── context.json          # modelo técnico, de sistema y humano
├── agent-context.md      # briefing para agentes de IA
├── index.html            # portal humano, sin servidor
├── state.json            # metadatos de freshness
└── graphify/             # grafo, informe y visualizaciones de Graphify
```

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

## Licencia

Apache-2.0. Ver [LICENSE](LICENSE).
