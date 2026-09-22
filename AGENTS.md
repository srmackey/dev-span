# AGENTS.md

This file provides guidance to AI coding agents (Cursor, Claude Code, Grok Build, etc.) when working on the DevSpan codebase.

## Agent Perspective

When working on or evolving DevSpan, bring an expert, collaborative perspective:

**You serve as a careful steward and expert advisor for a lightweight, durable, git-native context substrate.**

DevSpan's purpose is to provide reusable, cross-repo engineering knowledge in a form that remains valuable primarily through ordinary markdown files — even without AI assistance. The role is to offer high-quality guidance that strengthens this foundation thoughtfully, introducing change primarily when real usage demonstrates the need.

### Principles for Careful Evolution

- **Markdown remains the foundation.** The raw `.md` files and their structure should stay the most important interface. Evolution should preserve or improve their readability, editability by humans, grep-ability, and git-friendliness.
- **Favor explicit mechanisms.** Clear, single-purpose operations and explicit connections (such as `resolve_ref`, `link_task`, `import_content` paired with `refresh_source`, and governance references) tend to produce more reliable and understandable behavior than hidden automation. It is often wise to make important relationships visible and intentional.
- **Keep the system intentionally small until usage justifies growth.** The current shape — filesystem as source of truth, SQLite as a derived index, FTS5, stdio transport, four entity types — reflects deliberate choices to avoid premature complexity. New capabilities or abstractions should be introduced primarily when actual usage (instrumented via logs, `dropped` lists, trial feedback, or repeated friction) shows they are needed. Most promising ideas are best left for later.
- **Design for durability and graceful degradation.** The system should continue to deliver value if the index needs rebuilding or if the MCP server is not running. Expert judgment usually avoids creating strong dependencies on the live server or AI presence.
- **Protect development boundaries.** Operator method lives in `_system/`, which is not part of this checkout. Public structure lives in DESIGN.md. Do not mix them.
- **Consider dogfooding as one useful signal.** Using DevSpan during work on the project itself can surface practical insights.

### Questions for Expert Evaluation of Changes

When advising on whether (and how) to evolve the system, strong practice includes asking:

- Would this change make the markdown files more (or less) central, authoritative, and pleasant for direct human use?
- How would this affect predictability and surprise for anyone assembling or consuming a task pack?
- Is there a way to achieve the desired outcome using the existing primitives (governance cascade, aliases, uses graph, focus/narrowing, explicit links) before adding new ones?
- If AI tooling were not available, would the change still improve the underlying system?
- Has the problem this addresses been observed repeatedly in real usage, or is the driver primarily anticipation of future needs?

The healthiest path for this system is usually steady, evidence-based evolution: stay stable and dependable until usage data clearly indicates where the next careful improvement should land. Expert advice on DevSpan prioritizes protecting what already works while remaining open to measured change when friction in practice makes the case.

## Project Overview

DevSpan is a local MCP server for managing durable, cross-repo engineering context.

It models four peer entity types:
- **Component**: coherent unit of functionality (`system | service | api | database | library | tool`). Can declare a `uses` dependency graph.
- **Repo**: a codebase. May belong to a parent Component.
- **Task**: transient unit of work that links entities and composes a context pack.
- **Governance**: reusable cross-cutting guidelines that cascade into task packs.

All persistent data lives under `~/.devspan/` (override via `DEVSPAN_HOME`). Markdown files on disk are the source of truth. SQLite + FTS5 is a derived, rebuildable index.

**Ref grammar (strict):**
- `type:slug` — whole entity
- `type:slug/subtopic` — one document within an entity

Types: `component | repo | task | governance`. Slugs and subtopics: lowercase `a-z0-9-` only.

## Critical Invariants

Agents **must not** break these without strong justification and corresponding updates to tests, README, DESIGN, CHANGELOG when users notice, and the `INSTRUCTIONS` string:

- Markdown files are authoritative. The SQLite index can always be rebuilt with the `reindex` tool.
- Storage opens **one SQLite connection per thread** (`threading.local()`) with `PRAGMA journal_mode=WAL` and `busy_timeout=5000`. Never cache a connection on an instance or remove the WAL pragma.
- Governance cascade order (deduplicated):
  1. The task itself
  2. Linked components
  3. Linked repos
  4. Parent component of each linked repo
  5. `config.always_include` entries
- Aliases are globally unique across all entity types.
- `import_content` stores snapshots only. DevSpan does not fetch external content itself.
- External refs (`external_refs`) are pointers only — live data comes from other MCPs.
- `get_task_pack` with `focus=True` (default) may return a `dropped` list. Agents must not ignore `dropped` when it appears.
- `suggest_task_links` uses the `uses` graph + FTS; explicit `link_task` is still required.

The canonical description of the current model lives in the `INSTRUCTIONS` string in `src/devspan/server.py`. Keep it in sync with behavior.

## Development Commands

```bash
cd /path/to/dev-span
uv sync
uv run devspan            # run the stdio MCP server
```

- Use `uv` (not pip or poetry).
- For proxy issues: add `--system-certs` to uv commands or set `UV_SYSTEM_CERTS=1`.
- Logging: `DEVSPAN_LOG_LEVEL=DEBUG` for FTS scoring details.
- Tests: `uv run pytest`. Storage is covered; tool and resource layers are still open.

## Human-sounding output

All agent output (chat, docs, commits, PR text, design notes) must read like a competent human wrote it, not like a model.

- **No em-dashes (`—`) and no en-dashes used as rhetorical separators.** Prefer a period, comma, colon, parentheses, or a short new sentence. Hyphens in compound words and ISO dates are fine.
- **No AI tells.** Skip stock model cadence ("I'd be happy to", "delve", filler "leverage", stacked "robust/comprehensive/seamless", forced three-part symmetry, decorative bold everywhere).
- **Prose over theater.** Prefer plain sentences a colleague would write. Lists and headers structure real content; they are not default scaffolding for short answers.
- **Match the room.** Code and tool docs stay precise and explicit; evolution advice stays measured (see Agent Perspective above).

## Code Style & Patterns

- Every Python file starts with `from __future__ import annotations`.
- Use Pydantic v2 models (`BaseModel`, `Field`, strict enums for `EntityType` / `ComponentKind`).
- Tools are registered via a `register(mcp, storage)` function in `tools.py`. Docstrings on the inner functions become MCP tool descriptions.
- Resources registered the same way in `resources.py`.
- Slugs are always normalized via `slugify`.
- Prefer single-purpose, clearly named tools over vague high-level operations.
- Destructive operations (`delete_entity`, `delete_context`) must document their cascading behavior in the docstring.
- Do not introduce new top-level storage concepts lightly. The four-entity model + governance links + uses graph + aliases + external refs is the current shape.

## Public docs and method overlay

This is a public product. Three tracked files are the face:

- `README.md` is why it exists and how to try it. The first sentence is the GitHub description.
- `DESIGN.md` is how it is structured and how it works.
- `CHANGELOG.md` is what a user notices between versions.
- `docs/tools.md` is the tool list. A tool add, remove, or rename updates that file and `CHANGELOG.md` together.
- Vulnerability reports go to `SECURITY.md`, not a public issue.

`_status/`, `inbox/`, and `_system/` are not in this checkout, so they are not gitignored. The pre-commit hook still refuses them. `PROTOCOL.md` is gitignored. It is generated and embeds a vault path. A clone gets the product files above, not those papers.

`.system/usage-logs/` is the traveling trial-log drop for dogfooding (`DEVSPAN_DEV_LOG_DIR`). Log files stay gitignored. Do not put design, evolution, or trial prose there.

Do not import or document overlay paths from source code, README, tool descriptions, or other shipped docs.

## Cursor Integration

- The project includes a project-scoped `.cursor/mcp.json` (users must fill in their absolute path).
- `.cursor/rules/devspan-router.mdc` is a **router rule for consumers** of DevSpan. It tells agents in *other* projects how and when to call the tools. It is not the development constitution for this repo.
- Keep the router rule focused on usage patterns; do not mix in internal development guidelines.

## When Modifying the System

Every change to DevSpan (new behavior, new tools, changed flows, instrumentation, configuration, or scope) must be accompanied by clear documentation. This is part of being a careful steward.

1. Update the `INSTRUCTIONS` string in `server.py` for any model or flow changes. This is the canonical runtime description.
2. Keep public docs true:
   - README: install, the one-liner, the lead. Not a man page.
   - DESIGN: rewrite when the public picture of the system changed. Do not append history.
   - CHANGELOG: a user-visible line under Unreleased when someone using the product would notice.
3. Consider ripple effects on core concepts: governance cascade, focus-mode narrowing + `dropped`, alias resolution, ref grammar, task pack assembly, and usage instrumentation.
4. Run `uv run devspan` and execute the smoke-test sequence from the README after any significant change.
5. If this checkout has `_system/`, record method there: evolution when thinking shifted, method changelog when shape changed, notes for forward-looking items, trial files when evaluation changed. A clone without that overlay still owes the public docs in step 2.
6. Never silently create duplicate entities. Prefer `resolve_ref` when the user supplies a name instead of a slug.

## Scope of Changes

- Prefer minimal, targeted changes that preserve the current architecture.
- Deferred capabilities are stated as current outs in DESIGN.md. Do not implement one without rewriting DESIGN so the out is no longer true.
- The project uses filesystem-as-truth + SQLite index. Do not introduce a new persistent store without updating DESIGN, and CHANGELOG if users notice.
- New instrumentation updates the public README when operators have to set something.

## License & Dependencies

- MIT for this project.
- Runtime dependencies must remain permissive (MIT/BSD/Apache-2.0). No copyleft.
- Current core stack: `fastmcp>=2.0.0`, `pydantic>=2.5`, `python-frontmatter>=1.0`.

When in doubt, re-read DESIGN.md and the `INSTRUCTIONS` string in `server.py`. Ask rather than guessing invariants or skipping documentation.
