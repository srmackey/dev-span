# Changelog

All notable changes to DevSpan are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed

- Renamed the product from ContextForge to DevSpan. Package, CLI, and MCP id are `devspan`. Store is `~/.devspan/` (override `DEVSPAN_HOME`). GitHub: [srmackey/dev-span](https://github.com/srmackey/dev-span).
- Public docs now follow the product triple: [DESIGN.md](DESIGN.md) is the structure, this file is what moved, [README.md](README.md) is the draw. Contributor method files live under `_system/` and are not shipped.

## [0.1.0] - 2026-07-17

### Added

- Local FastMCP server over stdio, `uv run contextforge`.
- Four peer entity types: Component, Repo, Task, Governance. Markdown under `~/.contextforge/` is the source of truth; SQLite + FTS5 is a rebuildable index.
- Ref grammar `type:slug` and `type:slug/subtopic`. Globally unique aliases. `resolve_ref` for fuzzy lookup.
- `get_task_pack` with governance cascade and optional FTS focus-mode (`dropped` lists filtered subtopics).
- `suggest_task_links` over the component `uses` graph.
- `import_content` / `refresh_source` / `list_stale_sources` for snapshots fetched elsewhere. `external_refs` as pointers only.
- `bind_workspace` / `get_current_workspace` instead of an MCP Roots handshake.
- Persistent rotating log at `~/.contextforge/logs/contextforge.log`. `tail_logs` inside the server.
- Storage test suite (entities, aliases, links, graph, delete, reindex, search, subtopics, task packs).
