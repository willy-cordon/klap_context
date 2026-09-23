# Sistema visual del portal KlapContext

Esta guía preserva la identidad del portal generado en `.klap/index.html`.
No es una captura de pantalla: es el contrato de producto y diseño para cambios futuros.

## Intención

KlapContext explica un sistema de ingeniería. La interfaz debe sentirse como una
consola técnica clara y confiable, no como un dashboard de health-score ni como
una copia de Graphify o Grasp.

Principios:

1. **Comprensión antes que métricas.** Priorizar propósito, story, flujos,
   puntos de entrada y evidencia.
2. **Evidencia visible.** Distinguir hechos, inferencias e incógnitas; no
   ocultar información que no pudo determinarse.
3. **Densidad ordenada.** Usar paneles compactos, bordes sutiles y tipografía
   monoespaciada para metadata, sin convertir la portada en un grafo.
4. **Exploración delegada.** El grafo profundo y call flows siguen siendo de
   Graphify; KlapContext enlaza a ellos.
5. **Idioma.** La experiencia generada para este producto se redacta en
   español. Los nombres propios, rutas y símbolos de código se conservan.

## Estructura estable

```text
Barra superior
├── Marca KlapContext
├── Repositorio
├── Estado de contexto
└── Copiar contexto de agente

Rail lateral
├── Señal de cobertura (puntos/evidencias)
└── Navegación por comprensión

Área principal
├── Hero: nombre, stack y propósito
├── Señales: entry points, flows, evidencias
├── Sistema: story, flujos, entradas/salidas, capacidades
├── Operación: procesos, deployment, exploración técnica
└── Confianza: incertidumbres y evidencia

Panel lateral derecho
└── Acción y recordatorio de contexto para agentes
```

## Tokens visuales

Definidos en `src/klapcontext/portal.py`:

| Token | Uso |
| --- | --- |
| `--bg` | Fondo azul muy oscuro |
| `--card` | Superficie de panel |
| `--line` | Separadores y bordes |
| `--cyan` | Acciones, evidencia activa y estado |
| `--violet` | Nodos, metadata y acento secundario |
| `--amber` | Avisos o información que requiere atención |

Mantener contraste alto. No reemplazar esta paleta por blanco, gradientes
decorativos grandes ni colores de severidad como elemento dominante.

## Componentes obligatorios

- Hero con stack y estado (`ACTUAL` o `SIN COMMIT`).
- Acción **Copiar contexto** con feedback inmediato.
- Paneles omitidos cuando no hay contenido, salvo las incertidumbres: estas
  deben mostrarse cuando existan.
- Flujos como secuencias lineales, no como una reimplementación del grafo.
- Links explícitos a las visualizaciones de Graphify cuando estén disponibles.

## Cambio seguro

Al modificar `portal.py`:

1. Mantener HTML estático, sin servidor ni framework frontend.
2. Preservar la operación desde `file://` y el copy-to-clipboard.
3. Ejecutar `klap update .` y revisar `.klap/index.html`.
4. Ejecutar `python -m pytest -q`.
5. No introducir secciones vacías ni afirmaciones sin evidencia.
