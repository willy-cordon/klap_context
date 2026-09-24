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

- `providers/`: contrato para motores de análisis. `GraphifyProvider` adapta el
  motor actual sin acoplarlo al modelo del sistema.
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

- Graphify es evidencia/proveedor; no es la interfaz de producto.
- Ninguna heurística se presenta como un hecho confirmado.
- Los analizadores deben ser determinísticos antes de añadir inferencias.
- Los artefactos se generan una vez mediante `init`/`update`; navegar el portal
  no vuelve a analizar el repositorio.
