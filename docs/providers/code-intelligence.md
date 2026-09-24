# Evaluación de proveedores de inteligencia de código

Evaluado el 2026-09-23. Ningún proveedor externo es una dependencia de
KlapContext: el análisis base debe funcionar aunque no estén instalados.

| Proyecto | Licencia | PHP | Capacidades relevantes | Decisión |
| --- | --- | --- | --- | --- |
| [aft-mcp](https://github.com/dazarodev/aft-mcp) | MIT | Declarado | Outline, símbolo, callers, call tree, impacto, trazas y búsqueda estructural | Candidato opcional futuro; no es dependencia de KlapContext. |
| [treesitter-mcp](https://github.com/Christoph/treesitter-mcp) | MIT | No declarado | Contexto mínimo, mapa, usos, call graph e impacto con budget | No integrar aún: no cubre el primer objetivo Laravel/PHP. |

## Decisión Sprint 2

Se eligió `tree-sitter` + `tree-sitter-php` como dependencia local del
provider `php-tree-sitter`. Ambos tienen licencia MIT, soporte PHP y wheels
para el binding Python. Esto mantiene el índice dentro de KlapContext, evita
un proceso MCP obligatorio y permite cachear símbolos/relaciones bajo
`.klap/code-intelligence/`.

Capacidades activas: `SYMBOL_LOOKUP`, `CALLERS`, `CALLEES`, `CALL_GRAPH`,
`IMPACT_ANALYSIS` y `MINIMAL_EDIT_CONTEXT`.

## Criterio de integración

Un provider sólo se agrega si aporta una capacidad que reduzca de forma
medible el código que un agente necesita leer para completar una modificación.
La interfaz interna pregunta por capacidades (`CALLERS`, `IMPACT_ANALYSIS`,
`MINIMAL_EDIT_CONTEXT`), nunca por el nombre de una herramienta externa.

## Límites conocidos

- Los call graphs de ambos proyectos son análisis estructurales/best effort,
  no resolución semántica de compilador.
- `aft-mcp` se distribuye como MCP local mediante npx, binarios o Cargo; la
  instalación queda fuera del flujo base de KlapContext.
- La resolución de llamadas es estructural y conservadora: las relaciones que
  no pueden resolverse por tipo quedan como `INFERRED`.
