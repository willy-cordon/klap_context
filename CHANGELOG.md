# Changelog

## 0.10.1 — 2026-10-14 — Windows Archify evidence paths

- Normalizes Windows backslashes in repository evidence to the repo-relative
  POSIX paths required by Archify.
- Rejects absolute, parent-traversal and environment-file evidence paths before
  they reach the renderer.
- Keeps Serena installation and lifecycle behavior unchanged.

## 0.10.0 — 2026-10-14 — Archify flow diagrams

- Adds Archify 3.1.0 as a pinned, integrity-verified, project-local renderer
  that remains separate from KlapContext's analysis-provider registry.
- Projects evidenced static-analysis flows to reproducible Archify workflow IR
  and standalone interactive HTML without requiring an AI agent at runtime.
- Adds an offline **Flujos** portal section with diagram selection, evidence,
  confidence, limitations, stale-state reporting and standalone artifact links.
- Adds automatic lifecycle management, Node.js compatibility checks,
  `--no-archify`, persistent `.klap/archify.json` settings and doctor output.
- Keeps context generation usable when installation, validation or rendering
  fails, and retains the last valid diagrams explicitly marked as stale.

## 0.9.0 — 2026-10-13 — Managed standard providers

- Makes Graphify and Serena standard `klap init` providers, prepared in isolated
  per-project runtimes with pinned versions and reproducible lifecycle state.
- Adds `--no-graphify`, `--no-serena`, and `klap doctor --agent --repair` while
  preserving explicit project opt-outs and native-analyzer fallback.
- Verifies Graphify executability and Serena's public MCP handshake, tool
  discovery and bounded read-only overview before reporting a provider ready.
- Keeps managed runtime, Serena cache and generated context private through
  `.git/info/exclude`; no global PATH, agent configuration or Python runtime is
  modified.

## 0.8.3 — 2026-10-11 — Functional project portal

- Makes the offline portal identify the analyzed repository instead of using
  reference-design labels.
- Replaces hidden single-view navigation with durable, keyboard-accessible
  section anchors and a sticky active navigation bar.
- Connects the console controls and map to real report actions and evidence.

## 0.8.2 — 2026-10-11 — Agent context dependency fix

- Renders normalized dependency records safely when a project reports
  `name`/`category` instead of framework-manifest `package`/`scope` fields.

## 0.8.1 — 2026-10-11 — Portal compatibility fix

- Fixes the offline portal navigation template for Python 3.10 and 3.11.
- Publishes the Charcoal + Cyan console portal under the matching package version.

## 0.7.0 — 2026-10-10 — Pluggable Analysis Providers

- Introduces capability-based provider contracts, registry, resolver, normalized
  results and provider provenance without coupling Agent Intelligence to an
  implementation.
- Makes Graphify optional and automatic when available, with native fallbacks,
  scope-safe extraction and reliable restoration of temporary ignore rules.
- Adds an optional, read-only Serena MCP adapter for semantic symbol,
  definition, reference, implementation and impact queries.
- Extends KlapContext's MCP server with code-navigation, dependency, impact and
  endpoint-flow tools backed by the available providers.
- Adds portable project-local provider configuration, richer diagnostics and
  documentation covering installation, capabilities, security and limits.

## 0.6.0 — 2026-09-27 — Context Reliability

- Adds a central, configurable Index Scope applied before Graphify and reused
  by adapters, exploration, impact and recommendations.
- Ignores commented/string-embedded Laravel routes and schedules while
  recording disabled declarations separately.
- Adds normalized injection, dispatch and listener relationships with
  explainable reverse-impact paths.
- Centralizes freshness around commit, eligible-content hash and scope rules.
- Replaces the MCP process smoke test with initialize, tool discovery and a
  minimal `graph_stats` call.
- Stores new graphs canonically in `.klap/graphify-out`; legacy copies are only
  migrated by explicit command and are preserved as backups.

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
