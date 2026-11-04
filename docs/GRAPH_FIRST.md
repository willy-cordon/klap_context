# Migración graph-first

## Cambios incompatibles intencionales

- Eliminados Serena y Archify: módulos, adapters, instalación, diagnóstico y
  ejecución. Se retiran `--no-serena`, `--no-archify` y los parámetros Python
  equivalentes. `--no-graphify` se conserva.
- El estado nuevo ya no incluye `renderers.archify`; el ciclo de proveedores
  administra únicamente Graphify. Configuración de proveedores desconocidos
  genera un aviso y no se ejecuta.
- El portal sólo navega a Inicio y Git. Los antiguos anchors de secciones
  técnicas desaparecen; sus hechos siguen en los artefactos para agentes.
- No se borran archivos antiguos del usuario: `.serena/`, runtimes, configuraciones,
  `archify-state.json`, diagramas ni exclusiones Git preexistentes. Quedan inertes;
  su eliminación manual es opcional. No se instala ni ejecuta ninguna herramienta
  retirada al actualizar.

## Probar con un repositorio real

Desde esta rama, instalar `python -m pip install -e .`. Luego:

```bash
klap init /ruta/al/repositorio
klap open /ruta/al/repositorio
klap update /ruta/al/repositorio
```

Abrir también `/ruta/al/repositorio/.klap/index.html` sin conexión. Comprobar
zoom, arrastre, selección, búsqueda, Conexiones, Ajustar y Git. Verificar nombres
y relaciones contra `.klap/graphify-out/graph.json`. Si falla Graphify, Inicio
muestra su indisponibilidad y el resto del contexto continúa disponible.

## Límites

- Las relaciones son evidencia estática, no ejecución observada. Identificadores
  ausentes/duplicados y aristas sin extremos válidos no se dibujan.
- El portal conserva el layout y las comunidades producidas por Graphify. Para
  evitar ruido visual, omite únicamente nodos externos sin archivo fuente; el
  grafo canónico completo sigue disponible para MCP y análisis técnico.
- Grafos extremadamente grandes todavía tienen un costo de carga/memoria
  proporcional al total de registros mostrados.
- No hay un LSP externo: las operaciones no soportadas por los analizadores
  existentes se declaran como tales.
- El portal integra el HTML nativo de Graphify y sustituye su carga CDN de
  vis-network 9.1.6 por una copia local. Su SHA-384 coincide con el SRI del
  exportador:
  `Ux6phic9PEHJ38YtrijhkzyJ8yQlH8i/+buBR8s3mAZOJrP1gwyvAcIYl3GWtpX1`.
- `init` y `update` usan `extract --code-only` con comunidades habilitadas;
  no se agregan ni se modifican relaciones para mejorar el diseño.
- Graphify se administra a partir de la versión 0.9.102. Los runtimes
  anteriores se reemplazan automáticamente en el siguiente `init` o `update`;
  si la extracción falla, KlapContext declara el fallo y activa el fallback,
  sin presentar un grafo viejo como nuevo.
