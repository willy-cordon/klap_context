# Proveedores de análisis

El contexto para agentes y MCP resuelve capacidades mediante `AnalysisServices`,
con analizadores nativos como fallback. El portal humano es graph-first: la CLI
le entrega el grafo ?nicamente cuando el resultado exitoso proviene de Graphify;
no presenta el fallback nativo como si fuera un grafo de Graphify.

## Capas

```text
CLI / portal / MCP
        ↓
AnalysisServices
        ↓
CapabilityResolver ── trazas, timeout, fallback, warnings
        ↓
ProviderRegistry ── prioridad/capacidad, idioma, framework, enabled
        ↓
adapters Graphify | analizadores nativos | adapters externos
```

## Ciclo de vida estándar

`providers/lifecycle.py` prepara los binarios estándar antes de componer el
registry, pero no participa en la resolución de capacidades. Usa entornos
aislados por proyecto en `.klap/provider-runtime/`, con Graphify `0.9.102`,
como único runtime externo administrado. El estado
reproducible queda en
`.klap/provider-state.json`: versión requerida/instalada, origen, ejecutable,
estado de instalación, conexión, capacidades verificadas y último error.

Precedencia: `enabled:false` en `.klap/providers.json` impide toda preparación
persistente; `--no-graphify` omite el proveedor sólo para la
ejecución actual; en ausencia de esas opciones, los proveedores estándar se preparan.
Un fallo deja el resultado en `FAILED` o `PARTIAL` y el resolver mantiene los
proveedores nativos como fallback. No se modifican PATH ni configuraciones MCP
globales.

- `providers/contracts.py` contiene Protocols pequeños para símbolos,
  referencias, implementaciones, call graph, entry points, relaciones,
  dependencias y procedencia. Un adapter implementa sólo lo que soporta.
- `providers/models.py` contiene identidad, ubicación, relación, proveedor,
  evidencia, confianza, limitaciones y estados normalizados.
- `providers/registry.py` registra adapters en runtime. No hay que editar el
  resolver para agregar uno.
- `providers/resolver.py` filtra por idioma/framework, aplica prioridad por
  capacidad, disponibilidad dinámica, timeout y fallback explícito.
- `providers/graphify.py` es la frontera exclusiva de Graphify.
- `providers/native.py` conserva los analizadores locales. El fallback
  `klap-native` permite generar contexto aunque no haya grafo externo.

## Estados

- `OK`: el proveedor produjo un resultado utilizable.
- `NO_RESULTS`: la consulta fue soportada y terminó correctamente, sin hechos.
- `UNSUPPORTED`: no hay proveedor habilitado/compatible o el adapter no
  implementa esa operación.
- `PROVIDER_ERROR`: excepción, timeout o salida inválida del proveedor.
- `UNKNOWN`: el proveedor no pudo determinar una respuesta; no equivale a
  ausencia de resultados.

Los resultados incluyen `provider`, `confidence`, `evidence`, `limitations`,
`warnings` y `trace`. Si se usa fallback, la advertencia de degradación queda en
el contexto generado bajo `providers`.

## Composición y cobertura de `init`

El registry siempre registra `graphify`, `klap-native` y el adapter PHP. Que un
adapter esté registrado no significa que haya sido ejecutado. `klap init`
resuelve y ejecuta realmente `framework_analysis` y las capacidades agregables
de init antes de construir el contexto; `context_builder` recibe el modelo ya
compuesto y no vuelve a ejecutar analizadores por fuera del registry. Registra
en `context.json.analysis`:

- cobertura y cantidad de hechos por capacidad a partir de `ProviderResult`;
- proveedores detectados, ejecutados y omitidos, con invocaciones y motivos
  derivados de las trazas reales;
- hechos lossless bajo `analysis.contributions`, con procedencia, evidencia y
  confianza, además de su proyección compatible en `semantic_model`;
- política de composición aplicada y capacidades query-shaped no ejecutadas;
- estado global `COMPLETE` o `PARTIAL`. La ausencia/falla del grafo deja el
  análisis en `PARTIAL`, aunque el contexto nativo se haya generado.

Las capacidades de hechos independientes se **agregan**: símbolos, referencias,
implementaciones, entry points, relaciones estructurales, dependencias,
procedencia, tests, integraciones, automatizaciones y configuración. El resolver
ejecuta todos los proveedores compatibles, deduplica por identidad semántica o
ubicación y conserva proveedor, evidencia y confianza del hecho retenido.

Las capacidades cuyo resultado representa un modelo o respuesta derivada son
**single-provider con fallback**: grafo de dependencias, call graph,
callers/callees, análisis de framework, reconstrucción/búsqueda de paths,
impacto y contexto mínimo de edición. En ellas se respeta prioridad y sólo se
prueba el siguiente proveedor si el anterior no está disponible o falla; no se
mezclan grafos incompatibles.

Graphify aporta el grafo canónico y sus recorridos. Los analizadores nativos
aportan en la misma ejecución detección de stack/framework, entry points,
relaciones locales, dependencias, tests, integraciones, automatizaciones,
configuración y evidencia. El compilador de contexto consume esa composición;
no contiene ramas específicas de Graphify.

## Configuración local

`.klap/providers.json` es opcional y no contiene rutas globales ni credenciales:

```json
{
  "providers": {
    "graphify": {
      "enabled": true,
      "timeout_seconds": 120,
      "priorities": {"dependency_graph": 100}
    },
    "php-tree-sitter": {
      "enabled": true,
      "priorities": {"symbol_lookup": 50, "call_graph": 50}
    }
  }
}
```

Un proveedor no registrado genera una advertencia de configuración. Un adapter
sin restricción de idioma/framework es agnóstico y puede participar aunque el
lenguaje no haya sido detectado.

## Adapter externo mínimo

No requiere herencia; el registro valida capacidades explícitas:

```python
from klapcontext.providers import Capability, ProviderRegistry, ProviderResult, ResultState

class MySymbols:
    name = "my-symbols"
    capabilities = {Capability.SYMBOL_LOOKUP}

    def find_symbols(self, request):
        values = []  # traducir la salida externa a modelos normalizados
        return ProviderResult(ResultState.NO_RESULTS, values)

registry = ProviderRegistry()
registry.register(
    MySymbols(),
    priorities={Capability.SYMBOL_LOOKUP: 80},
    languages={"python"},
    timeout=10,
)
```

Para capacidades que varían según el proyecto, se puede implementar
`capabilities_for(request)`. Para disponibilidad dinámica, implementar
`is_available(request)`. Ninguno debe anunciar una capacidad que no pueda
ejecutar.
