# Agent Intelligence

La capa Agent Intelligence decide el contexto mínimo que un agente necesita
antes de modificar código. No analiza con LLM lo que puede obtenerse de forma
determinística.

```text
Consulta → Intent Router → Context Planner → Capability Router
                                              ↓
                                 providers disponibles / fallback
```

## Sprint 1

- `agent/intents.py`: clasifica `UNDERSTAND`, `CHANGE`, `DEBUG`, `TEST`,
  `REFACTOR` e `IMPACT` con reglas auditables en español e inglés.
- `agent/capabilities.py`: registry y router de capabilities, con estados
  `READY` y `UNAVAILABLE`; un provider opcional no bloquea el plan.
- `agent/planner.py`: selecciona sólo las capabilities y secciones necesarias
  por intención; valida `detail` y `max_tokens`.
- `agent/models.py`: modelo serializable `AgentContextPlan`, base del futuro
  compilador de contexto.

## Prioridad de compilación futura

1. Evidencia directa y entry points.
2. Flujos y símbolos vinculados.
3. Configuración y tests relevantes.
4. Dependencias y documentación periférica.

Al llegar al presupuesto se debe detener la recopilación; no se incluyen
archivos completos cuando un snippet o símbolo es suficiente.

## Próximos sprints

1. Semántica Laravel y reconciliación de relaciones de flujo.
2. Ranking explicable, token budget y contexto mínimo de edición.
3. Compiladores para task/change/debug/test context y CLI.
4. MCP de alto nivel, con un número pequeño de herramientas orientadas a tarea.

## Sprint 2

`providers/code_intelligence.py` usa Tree-sitter PHP local para indexar
símbolos, `CALLS`, `INSTANTIATES`, `EXTENDS` e `IMPLEMENTS`. El índice se
cachea por metadatos de archivos y se consulta bajo demanda para callers,
callees, call graph, impacto y contexto mínimo de edición. Las relaciones no
resueltas por tipo se entregan como `INFERRED`.

## Sprint 3: frontera agnóstica de framework

Agent Intelligence consume `EntryPoint`, `ExecutionTransition` y
`SemanticComponent`, nunca estructuras específicas de Laravel. Laravel es el
primer adapter completo; PHP sin framework sigue operando en modo `GENERIC`.
Esto permite que próximos adapters de FastAPI, Django o Express enriquezcan la
misma planificación, ranking y presupuesto de tokens sin acoplarlos al
framework.
