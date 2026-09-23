# Sistema visual del portal KlapContext

Esta guía preserva la identidad del portal generado en `.klap/index.html`.
Es el contrato de producto y diseño para cambios futuros.

## Intención

KlapContext explica un sistema de ingeniería. Debe sentirse como una consola
técnica clara y confiable: útil para entender un repositorio, no como un
dashboard de health-score ni como una copia de Graphify o Grasp.

Principios:

1. **Panorama antes que detalle.** La vista `Sistema` debe responder en una
   pantalla qué es el proyecto, cómo se conecta y qué requiere atención.
2. **El mapa es protagonista.** El mapa conceptual es la pieza visual central
   del inicio; muestra relaciones verificables, no inventa arquitectura.
3. **Detalles en vistas, no con scroll.** `Flujos`, `Entradas`, `Evidencias` y
   `Graphify` son vistas intercambiables en el mismo HTML estático y se pueden
   enlazar mediante hashes (`#flujos`, `#entradas`, etc.).
4. **Evidencia visible.** Distinguir hechos, inferencias e incógnitas. No
   ocultar aquello que no pudo determinarse.
5. **Idioma.** La experiencia se redacta en español; rutas, símbolos y nombres
   propios de código se conservan tal como aparecen en el repositorio.

## Estructura estable

```text
Barra superior
├── Marca KlapContext y propósito de la herramienta
├── Estado del contexto y repositorio

Rail izquierdo
├── Sistema (dashboard inicial)
├── Flujos
├── Entradas
├── Evidencias
└── Graphify

Vista Sistema (sin scroll como requisito de escritorio)
├── Nombre, propósito, stack y estado
├── Mapa conceptual del sistema
├── Métricas: entradas, flujos, hechos e incertidumbres
└── Ejecución y lectura recomendada

Rail derecho
├── Copiar contexto para agente
├── Hallazgos principales
└── Próximo paso sugerido
```

## Tokens visuales

Definidos en `src/klapcontext/portal.py`:

| Token | Uso |
| --- | --- |
| `--bg` | Fondo azul muy oscuro |
| `--panel` | Superficie de paneles |
| `--line` | Separadores y bordes |
| `--cyan` | Acciones, conexiones y estado activo |
| `--violet` | Acento secundario y metadata |
| `--amber` | Incertidumbres o atención requerida |

Mantener alto contraste y densidad ordenada. Los gradientes sólo deben dar
profundidad; nunca reemplazar la jerarquía o la evidencia.

## Componentes obligatorios

- Vista `Sistema` como dashboard compacto y no una pila de secciones largas.
- Mapa conceptual con leyenda y estado vacío honesto cuando no haya relaciones.
- Navegación lateral con una vista activa y hash actualizable.
- Acción **Copiar contexto** con feedback inmediato.
- Métricas con etiquetas explicativas; no utilizar scores opacos.
- Enlaces a Graphify sólo cuando los artefactos existan.

## Cambio seguro

Al modificar `portal.py`:

1. Mantener HTML estático, sin servidor ni framework frontend.
2. Preservar el funcionamiento mediante `file://`, deep links por hash y copy
   to clipboard.
3. Mantener el inicio dentro del alto de escritorio típico cuando haya una
   cantidad razonable de datos.
4. Ejecutar `PYTHONPATH=src python -m pytest -q`.
5. Generar o revisar `.klap/index.html` antes de publicar.
6. No introducir afirmaciones sin evidencia ni secciones vacías engañosas.
