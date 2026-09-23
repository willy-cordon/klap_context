# KlapContext

Make your repository understandable to humans and AI.

Humans joining an unfamiliar codebase and AI coding agents have the same initial problem: they first need to understand the system. KlapContext turns a repository into reusable, local engineering context.

```text
Repository
    ↓
KlapContext
    ↓
Engineering Context
    ├── Human Portal
    └── Agent Context
```

KlapContext uses [Graphify](https://github.com/Graphify-Labs/graphify) as its technical graph engine. It does not replace Graphify's parser, graph, or MCP server.

## Quick start

```bash
pipx install klapcontext
pipx install graphifyy
cd my-project
klap init
klap open
```

`klap init` writes only local, ignored outputs under `.klap/` and adds `.klap/` to `.git/info/exclude`—never `.gitignore`.

## Commands

| Command | Purpose |
| --- | --- |
| `klap init` | Build Graphify outputs and engineering context. |
| `klap update` | Re-run Graphify with its incremental update flag and regenerate outputs. |
| `klap status` | Compare generation commit and working tree with the current repository. |
| `klap open` | Open the static human portal in the default browser. |
| `klap agent` | Print the local Graphify MCP command/configuration. |

## Outputs

```text
.klap/
├── context.json          # versioned engineering context manifest
├── agent-context.md      # compact context for coding agents
├── index.html            # static human portal
├── state.json            # freshness metadata
└── graphify/             # copied Graphify graph/report/HTML outputs
```

Assertions are backed by evidence with `CONFIRMED`, `INFERRED`, or `UNKNOWN` status. Inferred architecture is guidance, not ground truth.

## Development

```bash
python -m pip install -e .
python -m pytest
```

Graphify integration is intentionally isolated in `klapcontext.graphify`, allowing unit tests to avoid running Graphify while `klap init` and `klap update` always invoke the real CLI.
