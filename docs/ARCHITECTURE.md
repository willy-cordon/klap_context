# Arquitectura de KlapContext

KlapContext convierte evidencia local de un repositorio en un modelo de sistema
comprensible. No reemplaza un motor de análisis de código ni presenta un grafo
como producto principal.

```text
Proveedor de análisis + detectores de framework
                 ↓
              Evidencia
                 ↓
            System Model
                 ↓
      Contexto humano y para agentes
```

## Piezas actuales

### Modelo semántico genérico (Sprint 3)

El núcleo no usa conceptos internos de Laravel. La secuencia de análisis es:

```text
Repositorio → detección de proyecto → inteligencia de lenguaje
           → adapter de framework → SemanticModel → flujos/contexto
```

- `semantic.py` define `EntryPoint`, `ExecutionTransition` y `SemanticComponent`.
- `frameworks/base.py` define el contrato `FrameworkAdapter`.
- `frameworks/laravel.py` traduce rutas, scheduler y convenciones Laravel a
  tipos genéricos como `HTTP_ENTRY`, `SCHEDULED_ENTRY`, `QUEUE_DISPATCH` y
  `EXTERNAL_CALL`.
- `frameworks/generic_php.py` conserva símbolos, llamadas y un entry point
  heurístico `main()` aun cuando no existe framework reconocido.

`context_builder.py` reconstruye flujos exclusivamente desde el
`SemanticModel`. Agregar un adapter futuro (por ejemplo FastAPI) no debe exigir
cambios en Agent Intelligence ni en esa reconstrucción.

- `providers/`: contrato para motores de análisis. `GraphifyProvider` adapta el
  motor actual sin acoplarlo al modelo del sistema.
- `providers/code_intelligence.py`: provider local Tree-sitter PHP que genera
  un índice cacheado de símbolos y relaciones estructurales por demanda.
- `detector.py`: detecta lenguaje, framework e infraestructura.
- `frameworks/laravel.py`: interpreta convenciones Laravel y `composer.json`.
- `evidence.py`: representa evidencia con archivo, línea, símbolo, snippet,
  estado y confianza. Los snippets de `.env*` nunca se emiten.
- `context_builder.py`: compone el `System Model`; sólo conecta resultados,
  no vuelve a escanear el grafo.
- `agent_context.py` y `portal.py`: renderizan el mismo modelo para agentes y
  personas.

## Fase 1 completada

- Detección Laravel y versiones PHP/Laravel desde `composer.json`.
- Rutas, comandos, scheduler, jobs, eventos, listeners y componentes Laravel.
- Dependencias Composer clasificadas por categoría y alcance.
- Evidencia navegable para declaraciones determinísticas.
- Provider adapter de Graphify como preparación para motores futuros.

## Próximas fases

1. Reconstrucción conservadora de flujos: eventos, jobs, persistencia e
   integraciones, distinguiendo `CONFIRMED` de `INFERRED`.
2. Integraciones y datos: configuración, migrations y clientes sin exponer
   secretos.
3. Contexto mínimo por tarea y comandos `klap context`.
4. Vistas específicas de integraciones, automatizaciones, datos y dependencias.

## Restricciones

## Agent Intelligence

La capa `agent/` planifica el contexto mínimo para una intención antes de
invocar proveedores. El detalle y el presupuesto de tokens son parte del plan,
no una decisión implícita de una herramienta. Ver
[AGENT_INTELLIGENCE.md](AGENT_INTELLIGENCE.md).

- Graphify es evidencia/proveedor; no es la interfaz de producto.
- Ninguna heurística se presenta como un hecho confirmado.
- Los analizadores deben ser determinísticos antes de añadir inferencias.
- Los artefactos se generan una vez mediante `init`/`update`; navegar el portal
  no vuelve a analizar el repositorio.
