# Changelog

## 0.5.0

- Adds safe, idempotent `AGENTS.md` onboarding with private and shared modes.
- Preserves existing team instructions and refuses malformed managed markers.
- Generates local Graphify MCP examples for Codex, Claude Code, Cursor and
  generic MCP clients without changing global configuration.
- Adds `klap doctor --agent` with freshness, path, graph and MCP readiness
  checks, plus an optional bounded MCP startup probe.
- Shows agent-readiness status in the existing portal.

## 0.3.2

- Fix `klap init` crashing after generation when `stack.project_type` is a scalar.
- Exclude scalar stack metadata from portal technology tags.

## 0.3.1

- Ignores commented PHP route declarations.

## 0.3.0

- Added Lumen route-group support, including inherited prefixes and middleware.
- Reports Lumen separately from Laravel, with accurate Composer evidence.
- Follows classic constructor injection when reconstructing PHP call flows.
- Counts Graphify `links` as graph relationships, alongside `edges`.
- Reuses generated `.klap/context.json` for focused `klap context` requests.
- Prunes dependency and generated directories before source scans, improving WSL performance.

## 0.2.1

- Added initial Lumen route detection and agent intelligence foundations.
