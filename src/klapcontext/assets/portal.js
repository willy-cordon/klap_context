/* Offline presentation of Graphify records, using Graphify's vis-network engine. */
(() => {
  'use strict';
  const raw = JSON.parse(document.querySelector('#graph-data').textContent);
  const palette = ['#71e5c1', '#7daeff', '#c7a0ff', '#ffc27a', '#ff8eac', '#8ed7ef'];
  const kinds = [...new Set(raw.nodes.map(n => n.kind))].sort();
  const colors = new Map(kinds.map((k, i) => [k, palette[i % palette.length]]));
  const byId = new Map(raw.nodes.map(n => [n.id, n]));
  const adjacency = new Map(raw.nodes.map(n => [n.id, new Set()]));
  raw.edges.forEach(e => { adjacency.get(e.from).add(e.to); adjacency.get(e.to).add(e.from); });
  const nodes = new vis.DataSet(), edges = new vis.DataSet();
  const network = new vis.Network(document.querySelector('#graph'), {nodes, edges}, {
    layout: {randomSeed: 42, improvedLayout: false},
    nodes: {shape: 'dot', size: 8, borderWidth: 1, font: {color: '#d9e5f5', size: 13, strokeWidth: 3, strokeColor: '#0b111b'}},
    edges: {color: {color: '#425777', highlight: '#b8ffe9'}, width: 0.8, arrows: {to: {enabled: true, scaleFactor: 0.35}}, smooth: false},
    interaction: {hover: true, keyboard: {enabled: true, bindToWindow: false}, hideEdgesOnDrag: true},
    physics: {solver: 'barnesHut', barnesHut: {gravitationalConstant: -4000, springLength: 140, avoidOverlap: 0.7}, stabilization: {iterations: 180, fit: true}}
  });
  let selected = null;
  const selection = document.querySelector('#selection');
  const focus = document.querySelector('#focus');
  const hint = document.querySelector('#hint');
  // Large graphs start with a bounded, degree-ranked view. Search covers ALL nodes.
  const LIMIT = 350;
  function display(ids) {
    const visible = new Set(ids);
    nodes.clear(); edges.clear();
    nodes.add(ids.map(id => {
      const n = byId.get(id), degree = adjacency.get(id).size;
      return {id, label: n.label, color: colors.get(n.kind), size: Math.min(18, 7 + Math.sqrt(degree)), shape: /file|module/.test(n.kind) ? 'diamond' : /class|interface/.test(n.kind) ? 'square' : 'dot'};
    }));
    edges.add(raw.edges.filter(e => visible.has(e.from) && visible.has(e.to)).map(e => ({...e})));
    hint.textContent = ids.length < raw.nodes.length ? `Vista parcial: ${ids.length} de ${raw.nodes.length} nodos · Buscá para explorar` : 'Arrastrá para explorar · Rueda para zoom';
    network.setOptions({physics: {enabled: true}});
    network.stabilize(180);
  }
  network.on('stabilizationIterationsDone', () => {network.setOptions({physics: false}); network.fit({animation: false});});
  function select(id) {
    selected = id;
    focus.disabled = false;
    const n = byId.get(id), related = adjacency.get(id);
    const title = document.createElement('strong'); title.textContent = n.label;
    const detail = document.createElement('span'); detail.textContent = [n.kind, n.path, n.line ? `línea ${n.line}` : ''].filter(Boolean).join(' · ');
    const relations = document.createElement('span');
    const relationKinds = [...new Set(raw.edges.filter(e => e.from === id || e.to === id).map(e => e.relation).filter(Boolean))];
    relations.textContent = relationKinds.join(' · ');
    selection.replaceChildren(title, detail, relations); selection.hidden = false;
    nodes.update(nodes.get().map(v => ({id: v.id, opacity: v.id === id || related.has(v.id) ? 1 : 0.18})));
    edges.update(edges.get().map(e => ({id: e.id, color: {color: e.from === id || e.to === id ? '#71e5c1' : '#253047'}, width: e.from === id || e.to === id ? 2 : 0.5})));
    network.selectNodes([id]);
  }
  function clearSelection() {
    selected = null; focus.disabled = true; selection.hidden = true;
    nodes.update(nodes.getIds().map(id => ({id, opacity: 1})));
    edges.update(edges.getIds().map(id => ({id, color: {color: '#425777'}, width: 0.8})));
  }
  function overview() {
    clearSelection();
    display([...byId.keys()].sort((a,b) => adjacency.get(b).size-adjacency.get(a).size || a.localeCompare(b)).slice(0,LIMIT));
  }
  function neighborhood(id) {
    display([id, ...[...adjacency.get(id)].slice(0, LIMIT-1)]);
    select(id);
  }
  network.on('click', event => event.nodes.length ? select(event.nodes[0]) : clearSelection());
  document.querySelector('#fit').addEventListener('click', () => network.fit({animation: true}));
  document.querySelector('#reset').addEventListener('click', overview);
  focus.addEventListener('click', () => {if(selected !== null) neighborhood(selected);});
  const search = document.querySelector('#search'), results = document.querySelector('#results');
  search.addEventListener('input', () => {
    const q = search.value.trim().toLocaleLowerCase(); results.replaceChildren();
    results.hidden = !q;
    if(!q) return;
    const matches = raw.nodes.filter(n => `${n.label} ${n.path}`.toLocaleLowerCase().includes(q)).slice(0,30);
    matches.forEach(n => {
      const b = document.createElement('button'); b.textContent = `${n.label} · ${n.path || n.kind}`;
      b.addEventListener('click', () => {neighborhood(n.id); results.hidden = true;}); results.append(b);
    });
    if(!matches.length) results.textContent = 'Sin coincidencias';
  });
  search.addEventListener('keydown', e => {if(e.key === 'Escape') results.hidden = true;});
  const legend = document.querySelector('#legend');
  kinds.forEach(kind => {const item = document.createElement('span'), dot = document.createElement('i'); dot.style.background = colors.get(kind); item.append(dot, document.createTextNode(kind)); legend.append(item);});
  let resizeTimer;
  new ResizeObserver(() => {clearTimeout(resizeTimer); resizeTimer = setTimeout(() => {if(!document.querySelector('#inicio').hidden){network.redraw();network.fit({animation:false});}}, 120);}).observe(document.querySelector('#graph'));
  overview();
})();
