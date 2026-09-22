# DevSpan

A local MCP server for durable, cross-repo engineering context. Markdown files are the source of truth. SQLite + FTS5 is a derived index. The store lives under `~/.devspan/` (override with `DEVSPAN_HOME`).

This file is the public picture of how the system is structured. Install and try-it steps are in [README.md](README.md). What moved between versions is in [CHANGELOG.md](CHANGELOG.md). Contributor rules are in [AGENTS.md](AGENTS.md).

## What it is for

A single task often spans several codebases plus services you do not own. DevSpan captures reusable facts once (how the gateway authenticates, how the UI repo tests, the company security policy) and composes a pack for the task at hand.

It is not a wiki product, not a team sync service, and not a memory extractor. If the index is rebuilt or the MCP server is down, the markdown files still work.

## Entities

Four peer types:

| Type | Role |
|---|---|
| **Component** | A coherent unit of functionality. Kind: `system`, `service`, `api`, `database`, `library`, or `tool`. May declare a `uses` graph of other components. |
| **Repo** | A codebase. May name a parent component. |
| **Task** | Transient work. Links entities and composes a pack. May carry `external_refs` (pointers to Jira, PRs, and the like). |
| **Governance** | Reusable cross-cutting guidelines. Referenced, not owned, by other entities. Cascades into task packs. |

## Refs

```
type:slug            # whole entity
type:slug/subtopic   # one document inside it
```

Types: `component | repo | task | governance`. Slugs and subtopics: lowercase `a-z0-9-`.

Aliases are globally unique across types. `resolve_ref` fuzzy-matches slugs, aliases, and names so a nickname does not silently create a duplicate.

## Storage

```
~/.devspan/
  components/{slug}/_meta.md, {subtopic}.md
  repos/{slug}/_meta.md, {subtopic}.md
  tasks/{slug}/_meta.md, {subtopic}.md
  governance/{slug}/_meta.md, {subtopic}.md
  .index/devspan.db
  config.json
  logs/devspan.log
```

Markdown is authoritative. `reindex` rebuilds SQLite. One SQLite connection per thread, WAL mode. Do not cache a connection on the storage instance.

New entities get scaffolded subtopics (overview, auth, testing, and so on). Unused files can be deleted.

`config.json` holds `always_include` governance refs and workspace bindings (`bind_workspace` / `get_current_workspace`).

## Task packs

`get_task_pack` is the main composition. It gathers the task, linked entities, and governance.

**Governance cascade** (deduplicated):

1. The task itself
2. Linked components
3. Linked repos
4. Parent component of each linked repo
5. `config.always_include`

**Focus mode** (default on): entity-level refs with more subtopics than `per_entity_top_k` are FTS-narrowed against the task. Dropped refs are listed in `dropped`. Callers must not ignore that list. `focus=False` returns the full pack.

`suggest_task_links` walks the `uses` graph and scores unlinked subtopics with FTS. Explicit `link_task` is still required.

## Import vs pointers

DevSpan does not fetch Confluence, Jira, or GitHub itself.

- `import_content` stores a snapshot the caller already fetched, with source URL and timestamp.
- `refresh_source` returns that URL so another MCP can re-fetch.
- `external_refs` on a task are pointers only. Live data comes from other servers.

## Invariants

- Markdown wins. The index is rebuildable.
- Destructive tools (`delete_entity`, `delete_context`) document their cascade in the docstring.
- `import_content` never hits the network.
- Runtime dependencies stay permissive (MIT / BSD / Apache-2.0). No copyleft.

The canonical runtime description of the model is the `INSTRUCTIONS` string in `src/devspan/server.py`. Keep it in sync with behavior.

## What it does not do

These are current outs, not a backlog dump:

- No vector / semantic search. FTS5 is the search. `sqlite-vec` is the revisit path if FTS starts missing.
- No HTTP/SSE, no multi-tenancy. Stdio, one user. Git-synced markdown is the share path until that stops working.
- No automatic workspace detection. `bind_workspace` is explicit.
- No rich editor, no auto-capture, no temporal queries ("what did I know last month").
- No background refresh daemon. `list_stale_sources` plus on-demand import is the loop.

## Runtime vs this repo

The product store is `~/.devspan/`. This git repo is the server, the tests, and the contributor docs. Do not treat the checkout as the vault.
