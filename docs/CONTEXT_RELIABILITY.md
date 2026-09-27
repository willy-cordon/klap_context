# Context Reliability

## Index Scope

KlapContext builds `IndexScope` before invoking Graphify. Candidate files come
from tracked files plus untracked files visible to Git; ignored code is omitted
unless explicitly included. Manifests are retained as dependency metadata but
not treated as application symbols by KlapContext.

The local configuration is `.klap/scope.json`:

```json
{
  "version": 1,
  "include": ["public/custom-runtime.js"],
  "exclude": ["legacy/**"]
}
```

Explicit includes can override default directory exclusions. `.git`, `.klap`
and `graphify-out` remain safety exclusions. Run `klap scope --json` for paths,
counts and reasons. Changing the configuration or rule version invalidates the
recorded snapshot.

## Freshness

`klap status`, `klap doctor` and generated context use the same service. A
snapshot is current only when HEAD, scope rules and the content hash of included
code/metadata match. Changes outside scope are reported as irrelevant and do
not invalidate the index.

## Canonical graph and migration

New generations write one canonical graph at
`.klap/graphify-out/graph.json`. Existing `graphify-out/` or
`.klap/graphify/` copies are reported but not removed automatically.

```bash
klap migrate-graph          # dry-run plan
klap migrate-graph --apply  # move verified Graphify-owned copies to backups
```

Unknown root directories are never moved. Applied migrations preserve data in
`.klap/backups/`.

## Active code and uncertainty

Laravel/Lumen route and scheduler extraction uses the installed PHP AST to
exclude declarations inside comments and strings. Disabled declarations are
recorded separately and do not increase operational metrics. Dynamic patterns
that cannot be resolved remain inferred or unresolved.

Impact output distinguishes direct calls/instantiation, dependency injection,
event dispatch/listening and transitive paths. A path describes static evidence,
not proof that runtime behavior or a future change will fail.

## MCP verification

`klap doctor --agent --probe-mcp` starts Graphify over stdio with the canonical
graph, performs MCP initialize, lists tools and calls `graph_stats`, then closes
the session. Diagnostics are emitted per stage and a partial startup is not
reported as a verified connection.
