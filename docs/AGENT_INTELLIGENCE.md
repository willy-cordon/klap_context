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

1. Provider opcional de inteligencia PHP y representación unificada de sus
   resultados como evidencia.
2. Semántica Laravel y reconciliación de relaciones de flujo.
3. Ranking explicable, token budget y contexto mínimo de edición.
4. Compiladores para task/change/debug/test context y CLI.
5. MCP de alto nivel, con un número pequeño de herramientas orientadas a tarea.
