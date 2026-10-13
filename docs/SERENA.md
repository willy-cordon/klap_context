# Integración opcional con Serena

KlapContext puede usar [Serena](https://github.com/oraios/serena) como proveedor
semántico **on demand** mediante su servidor MCP público por stdio. No importa
módulos internos de Serena ni cambia la configuración global del operador.

## Estado upstream verificado

Investigación realizada contra el repositorio y la documentación oficiales el
2026-10-09:

- versión estable publicada y paquete PyPI: `serena-agent 1.7.0`;
- `main` declara `2.0.0.dev0` y Python `>=3.11,<3.15`;
- v1.7.0 es la última versión MIT; desde v2 la aplicación Serena es
  GPL-3.0-or-later, mientras `src/solidlsp` continúa bajo MIT;
- KlapContext (Apache-2.0) no redistribuye, enlaza ni importa código de Serena:
  se comunica por el protocolo MCP con un proceso instalado separadamente por
  el usuario. Esta frontera evita incorporar Serena a la distribución de
  KlapContext; quienes redistribuyan una solución combinada deben revisar sus
  propias obligaciones de licencia (esto no constituye asesoramiento legal);
- comando estable: `serena start-mcp-server`; transporte stdio por defecto;
- el servidor es stateful y mantiene un solo proyecto activo;
- Windows, Linux y macOS están soportados. Serena 1.7.0 fue probado aquí en
  Windows 10 con Python 3.11. Los language servers pueden requerir Node/npm,
  PHP, Java, .NET u otros toolchains según el lenguaje;
- PHP usa Intelephense por defecto (alternativas: Phpactor, PHPantom y
  Devsense); JavaScript se analiza con el language server de TypeScript;
- el soporte de implementaciones y referencias depende del language server.
  Algunos lenguajes no implementan esas operaciones o tienen alcance parcial.

Fuentes: README, `pyproject.toml`, `LICENSE`, documentación de herramientas,
lenguajes, ejecución, clientes y configuración del repositorio oficial.

## Instalación administrada y separada

Seguí el procedimiento oficial, fuera de KlapContext:

```bash
uv tool install -p 3.13 serena-agent
serena init
serena --version
```

`klap init` usa Serena 1.7.0 fijado y lo instala sólo si hace falta en
`.klap/provider-runtime/serena/`; también instala `uv 0.13.0` en ese mismo
runtime porque algunos language servers oficiales de Serena lo requieren. No
modifica PATH ni el intérprete principal. Luego ejecuta un handshake MCP,
descubre `tools/list` y verifica un `get_symbols_overview` público, acotado a un
único archivo elegible. Esa verificación puede hacer que Serena cree
`.serena/project.yml` y descargue el language server necesario; el archivo y la
caché pertenecen a Serena, permanecen locales al proyecto y no se agregan al
artefacto de KlapContext. KlapContext los añade solamente a `.git/info/exclude`
(nunca al `.gitignore` compartido). `--no-serena` lo omite para la
ejecución actual; `enabled:false` en `.klap/providers.json` es el opt-out
persistente y no se sobrescribe.

## Configuración portable

`.klap/providers.json` es opcional:

```json
{
  "providers": {
    "serena": {
      "enabled": true,
      "mode": "auto",
      "timeout_seconds": 30,
      "command": "serena",
      "args": [
        "start-mcp-server",
        "--context=ide",
        "--enable-web-dashboard=false",
        "--open-web-dashboard=false"
      ],
      "max_results": 50,
      "max_answer_chars": 20000,
      "priorities": {
        "symbol_lookup": 80,
        "references": 80,
        "implementations": 80,
        "impact_analysis": 80
      }
    }
  }
}
```

- `mode: auto`: registra Serena si el comando es detectable.
- `mode: configured`: exige una entrada explícita además del comando.
- `enabled: false`: lo omite sin iniciar procesos.
- `command` y `args` no deben contener rutas de proyecto. KlapContext valida el
  root y agrega `--project <root>` en runtime; rechaza `--project` y
  `--project-from-cwd` configurados para evitar activar otro directorio.

No pongas rutas personales ni credenciales en un archivo compartido. Si el
comando no está en `PATH`, configurá una ruta local sólo en un
`.klap/providers.json` privado.

## Seguridad y lifecycle

El adapter:

1. inicia un proceso stdio con el SDK MCP oficial de Python;
2. ejecuta `initialize` y `tools/list`;
3. deriva capacidades exclusivamente de las tools anunciadas;
4. reutiliza una sesión/proceso por instancia de servicios;
5. aplica timeout, límites de caracteres/resultados y cierre limpio;
6. invalida una sesión que falla o vence para no reutilizar estado corrupto;
7. valida toda ruta de entrada y salida contra el root resuelto.

Allowlist invocable: `find_symbol`, `get_symbols_overview`,
`find_declaration`, `find_referencing_symbols`, `find_implementations`,
`get_current_config` y, sólo cuando el contexto lo expone, `activate_project`.
El modo normal activa por `--project` validado. Nunca se invocan automáticamente
tools de edición, archivos, shell, onboarding, dashboard ni memorias, aunque
Serena las anuncie.

### Handshake real observado

En el entorno temporal aislado se instaló `serena-agent 1.7.0` con Python 3.11
y se ejecutó el SDK MCP oficial (`ClientSession`, `stdio_client`):

- `initialize`: servidor `Serena`; el campo protocol/server version informado
  fue `1.28.1` (versión de su SDK MCP, no de la aplicación);
- `tools/list` en contexto `ide` con proyecto activo expuso 22 tools:
  `replace_content`, `replace_in_files`, `replace_symbol_body`,
  `insert_after_symbol`, `insert_before_symbol`, `search_for_pattern`,
  `get_symbols_overview`, `find_symbol`, `find_referencing_symbols`,
  `find_implementations`, `find_declaration`, `get_diagnostics_for_file`,
  `rename_symbol`, `safe_delete_symbol`, las seis tools de memorias,
  `onboarding` e `initial_instructions`;
- el adapter descartó todas salvo las cinco tools semánticas read-only
  equivalentes (`get_symbols_overview`, `find_symbol`,
  `find_referencing_symbols`, `find_implementations`, `find_declaration`).

La presencia de tools peligrosas en el servidor no las vuelve invocables: el
cliente vuelve a comprobar la allowlist en cada `call_tool`.

## Capacidades

| KlapContext | Tool Serena requerida | Semántica |
| --- | --- | --- |
| `symbol_lookup` | `find_symbol`, `get_symbols_overview` o `find_declaration` | lookup, overview, definición y navegación |
| `references` | `find_referencing_symbols` | referencias estáticas verificadas por Serena/LSP |
| `implementations` | `find_implementations` | sólo si aparece en `tools/list` |
| `impact_analysis` | `find_referencing_symbols` | referencias verificadas; impacto explícitamente inferido |

Una tool ausente produce `UNSUPPORTED`; una búsqueda válida sin coincidencias,
`NO_RESULTS`; un timeout o fallo de transporte, `PROVIDER_ERROR`. Cada hecho
conserva archivo, línea uno-based, símbolo/name path, evidencia, proveedor,
confianza y limitaciones. Los nombres duplicados se desambiguan por name path y
archivo, o se consultan todos si el cliente no restringe el path.

Serena no aporta al adapter un grafo de dependencias o flujos equivalente a los
contratos actuales. Esas capacidades siguen proviniendo de Graphify o de los
analizadores nativos; no se inventan a partir de búsquedas textuales.

## Superficie MCP de KlapContext

Un cliente conectado sólo a KlapContext dispone de:

- `klap_search_symbols`
- `klap_find_definition`
- `klap_find_references`
- `klap_find_implementations`
- `klap_dependencies`
- `klap_change_impact`
- `klap_flows_and_endpoints`

Todas aceptan límites de resultados/caracteres y, donde corresponde,
profundidad. `klap_flows_and_endpoints` usa `.klap/context.json` o composición
local existente; no fuerza búsquedas exhaustivas de Serena.

## Doctor y diagnóstico

```bash
klap doctor .
klap doctor . --probe-mcp
klap doctor . --repair
```

El primer comando distingue `configured`, `detected`, `enabled` y dependencias
faltantes sin iniciar Serena. `--probe-mcp` hace handshake, descubre tools y
reporta `startable`, capacidades, lenguajes detectados y errores. La ausencia o
falla de Serena nunca vuelve obligatorio al proveedor ni bloquea KlapContext.
`--repair` reinstala de forma explícita los runtimes estándar locales con las
versiones fijadas; no cambia instalaciones globales.

## Portal HTML

El portal muestra únicamente datos precompilados por `klap init/update`, con el
estado real de los proveedores de esa ejecución. No tiene transporte MCP ni
backend dinámico y no simula búsquedas Serena. Las consultas dinámicas se hacen
por la superficie MCP de KlapContext.

## Validación real de código fuente

Se usaron repositorios temporales, no los proyectos ni la configuración del
operador:

- PHP/Lumen: definición `ProcessRequestService` en línea 4; referencia
  verificada desde el constructor de `ProcessRequestController` en línea 9;
  definición `VtexService/searchOrderVtex` en línea 6; referencia verificada
  desde `ProcessRequestService/callVtex` en línea 19. El adapter marcó esa
  referencia como confirmada y el posible impacto como inferido. Primera
  ejecución fría: 121.7 s por descarga de Intelephense; ejecución posterior:
  15.7 s.
- TypeScript: definición `createOrder` en línea 5 y referencia desde la línea 7,
  ambas comparadas con el archivo fuente; overview real del archivo con
  funciones, clase, método y constante. Ejecución con language server ya
  preparado: 13.7 s.
- Lumen nativo: el MCP de KlapContext devolvió el endpoint `POST call-vtex` y
  su flujo precompilado; Serena no inventó la relación HTTP.

Los tiempos incluyen arranque/cierre del servidor de prueba. En el servidor MCP
de KlapContext la instancia queda cacheada por root (máximo ocho roots), por lo
que consultas sucesivas reutilizan el proceso y la sesión.

## Graphify vs Serena vs nativo

| Proveedor | Fortaleza | Momento | Límite principal |
| --- | --- | --- | --- |
| Graphify | grafo técnico/caminos | extracción opcional de init/update | estático y puede ser incompleto |
| Serena | símbolos, definiciones, referencias e implementaciones LSP | consulta explícita on demand | depende del language server; puede crear config/descargar LS al activar |
| Nativo | framework, endpoints, flujos, dependencias y fallback local | init/update y consultas | heurístico o Tree-sitter por lenguaje |

El resolver agrega hechos independientes con procedencia y mantiene respuestas
derivadas como single-provider con fallback; no ejecuta todos los proveedores
indiscriminadamente.
