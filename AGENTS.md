# AGENTS.md

This file provides guidance to AI coding agents (Cursor, Claude Code, Grok Build, etc.) when working on the ContextForge codebase.

## Agent Perspective

When working on or evolving ContextForge, bring an expert, collaborative perspective:

**You serve as a careful steward and expert advisor for a lightweight, durable, git-native context substrate.**

ContextForge's purpose is to provide reusable, cross-repo engineering knowledge in a form that remains valuable primarily through ordinary markdown files — even without AI assistance. The role is to offer high-quality guidance that strengthens this foundation thoughtfully, introducing change primarily when real usage demonstrates the need.

### Principles for Careful Evolution

- **Markdown remains the foundation.** The raw `.md` files and their structure should stay the most important interface. Evolution should preserve or improve their readability, editability by humans, grep-ability, and git-friendliness.
- **Favor explicit mechanisms.** Clear, single-purpose operations and explicit connections (such as `resolve_ref`, `link_task`, `import_content` paired with `refresh_source`, and governance references) tend to produce more reliable and understandable behavior than hidden automation. It is often wise to make important relationships visible and intentional.
- **Keep the system intentionally small until usage justifies growth.** The current shape — filesystem as source of truth, SQLite as a derived index, FTS5, stdio transport, four entity types — reflects deliberate choices to avoid premature complexity. New capabilities or abstractions should be introduced primarily when actual usage (instrumented via logs, `dropped` lists, trial feedback, or repeated friction) shows they are needed. Most promising ideas are best left for later.
- **Design for durability and graceful degradation.** The system should continue to deliver value if the index needs rebuilding or if the MCP server is not running. Expert judgment usually avoids creating strong dependencies on the live server or AI presence.
- **Protect development boundaries.** Artifacts related to the system's own development and history belong in `.system/`. Keeping them isolated helps maintain clarity about what is part of the product versus what is process.
- **Consider dogfooding as one useful signal.** Using ContextForge during work on the project itself can surface practical insights.

### Questions for Expert Evaluation of Changes

When advising on whether (and how) to evolve the system, strong practice includes asking:

- Would this change make the markdown files more (or less) central, authoritative, and pleasant for direct human use?
- How would this affect predictability and surprise for anyone assembling or consuming a task pack?
- Is there a way to achieve the desired outcome using the existing primitives (governance cascade, aliases, uses graph, focus/narrowing, explicit links) before adding new ones?
- If AI tooling were not available, would the change still improve the underlying system?
- Has the problem this addresses been observed repeatedly in real usage, or is the driver primarily anticipation of future needs?

The healthiest path for this system is usually steady, evidence-based evolution: stay stable and dependable until usage data clearly indicates where the next careful improvement should land. Expert advice on ContextForge prioritizes protecting what already works while remaining open to measured change when friction in practice makes the case.

## Project Overview

ContextForge is a local MCP server for managing durable, cross-repo engineering context.

It models four peer entity types:
- **Component**: coherent unit of functionality (`system | service | api | database | library | tool`). Can declare a `uses` dependency graph.
- **Repo**: a codebase. May belong to a parent Component.
- **Task**: transient unit of work that links entities and composes a context pack.
- **Governance**: reusable cross-cutting guidelines that cascade into task packs.

All persistent data lives under `~/.contextforge/` (override via `CONTEXTFORGE_HOME`). Markdown files on disk are the source of truth. SQLite + FTS5 is a derived, rebuildable index.

**Ref grammar (strict):**
- `type:slug` — whole entity
- `type:slug/subtopic` — one document within an entity

Types: `component | repo | task | governance`. Slugs and subtopics: lowercase `a-z0-9-` only.

## Critical Invariants

Agents **must not** break these without strong justification and corresponding updates to tests, README, INSTRUCTIONS, and the appropriate `.system/` files (evolution.md, design.md, TRIAL.md):

- Markdown files are authoritative. The SQLite index can always be rebuilt with the `reindex` tool.
- Storage opens **one SQLite connection per thread** (`threading.local()`) with `PRAGMA journal_mode=WAL` and `busy_timeout=5000`. Never cache a connection on an instance or remove the WAL pragma.
- Governance cascade order (deduplicated):
  1. The task itself
  2. Linked components
  3. Linked repos
  4. Parent component of each linked repo
  5. `config.always_include` entries
- Aliases are globally unique across all entity types.
- `import_content` stores snapshots only. ContextForge does not fetch external content itself.
- External refs (`external_refs`) are pointers only — live data comes from other MCPs.
- `get_task_pack` with `focus=True` (default) may return a `dropped` list. Agents must not ignore `dropped` when it appears.
- `suggest_task_links` uses the `uses` graph + FTS; explicit `link_task` is still required.

The canonical description of the current model lives in the `INSTRUCTIONS` string in `src/contextforge/server.py`. Keep it in sync with behavior.

## Development Commands

```bash
cd /path/to/context-forge
uv sync
uv run contextforge            # run the stdio MCP server
```

- Use `uv` (not pip or poetry).
- For proxy issues: add `--system-certs` to uv commands or set `UV_SYSTEM_CERTS=1`.
- Logging: `CONTEXTFORGE_LOG_LEVEL=DEBUG` for FTS scoring details.
- Tests: `uv run pytest`. A storage-focused test suite now exists (see design.md Code-quality backlog for current coverage and remaining gaps).

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

## .system Directory (Development Only)

**The `.system/` folder is strictly for the development of ContextForge itself.**

- It contains transient artifacts used while designing, evolving, and trialing this system:
  - `design.md` — **current state + the single roadmap.** Snapshot of what was built vs. intent, *plus* the one place for all forward-looking items (deliberately deferred, known limitations, code-quality backlog, near-term priorities).
  - `evolution.md` — **what changed and why.** Append-only decision history and rationale, organized by round. Does **not** hold standalone roadmap lists — forward-looking items live in design.md's roadmap; evolution records only *why* each was deferred, in the round that raised it.
  - `TRIAL.md` — **evaluation evidence.** Trial rubric, success criteria, friction log, instrumentation notes. It *feeds* the roadmap; it references design.md rather than restating gaps.
- These files are **not** part of the shipped product, the user-facing documentation, or the runtime behavior.
- **Nothing else in the project may reference files inside `.system/`** (see rules below).

### Agent Responsibility
When modifying the system, agents are expected to maintain the internal development record in `.system/`. This is how we keep evolution evidence-based. See the ["When Modifying the System"](#when-modifying-the-system) section for the required documentation steps.

### Strict Rules
- Do not import, link to, or document `.system/` contents from source code, README.md, tool descriptions, or any permanent documentation.
- Do not add references to `.system/` files when updating the MCP contract, Cursor rules, or examples.
- When agents need historical context, they may read the files directly during a session, but must never make them visible or durable in the rest of the codebase.
- If you need to promote something from `.system/` into permanent docs, extract the content and place it in README.md or a new appropriate location — do not create cross-references.

Treat `.system/` like a scratchpad for the project's own builders. Never treat the files inside it as optional.

## Cursor Integration

- The project includes a project-scoped `.cursor/mcp.json` (users must fill in their absolute path).
- `.cursor/rules/contextforge-router.mdc` is a **router rule for consumers** of ContextForge. It tells agents in *other* projects how and when to call the tools. It is not the development constitution for this repo.
- Keep the router rule focused on usage patterns; do not mix in internal development guidelines.

## When Modifying the System

Every change to ContextForge (new behavior, new tools, changed flows, instrumentation, configuration, or scope) must be accompanied by clear documentation. This is part of being a careful steward.

1. Update the `INSTRUCTIONS` string in `server.py` for any model or flow changes. This is the canonical runtime description.
2. Keep README.md up to date:
   - Add or update tool descriptions, parameters, and examples.
   - Update smoke-test steps when behavior or required sequence changes.
   - Document any new environment variables, file locations (e.g. logs), or usage patterns.
3. Consider ripple effects on core concepts: governance cascade, focus-mode narrowing + `dropped`, alias resolution, ref grammar, task pack assembly, and usage instrumentation.
4. Run `uv run contextforge` and execute the smoke-test sequence from the README after any significant change.
5. **Document the change in the appropriate `.system/` files** (this is mandatory for any real evolution):
   - Append a clear, dated entry to `evolution.md` (the append-only decision log). Include what was changed, alternatives considered, rationale, and alignment with the principles above. Do **not** start standalone "future work" lists here — put forward-looking items in the design.md roadmap and keep only the *why* in the round.
   - Refresh `design.md` (the full current-state description, code-quality backlog, and `## Roadmap`) when the picture of what has been built vs. what is still needed changes, when key decisions are made, or when the "current state vs. original prompt" picture shifts. Update the Roadmap section whenever an item is deferred, completed, or re-prioritized. The code-quality backlog must be kept accurate for things like test coverage, transaction safety, etc.
   - Update `TRIAL.md` whenever the change affects how the system is evaluated, instrumented, or trialed (new signals such as logs, new `dropped` behavior, new governance or focus mechanics, etc.).
   See the dedicated [`.system/ Directory`](#system-directory-development-only) section for the purpose and strict rules around these files.
6. Never silently create duplicate entities. Prefer `resolve_ref` when the user supplies a name instead of a slug.

## Scope of Changes

- Prefer minimal, targeted changes that preserve the current architecture.
- Deferred items (vector search via sqlite-vec, HTTP/SSE, rich UI, etc.) live in the `design.md` → `## Roadmap`. Do not implement them without:
  - Moving the item out of the roadmap's "Deliberately deferred" list in `design.md` (to current-state / done)
  - Recording the decision and rationale in `evolution.md`
- The project deliberately uses filesystem-as-truth + SQLite index for git-friendliness and simplicity. Do not introduce new persistent stores without strong justification and the corresponding updates to `.system/` documentation + README.
- Any addition of instrumentation (new logs, new signals for `dropped`/focus/governance, etc.) must update both the implementation docs in `.system/` (especially `TRIAL.md` and `evolution.md`) and the public README.

## License & Dependencies

- MIT for this project.
- Runtime dependencies must remain permissive (MIT/BSD/Apache-2.0). No copyleft.
- Current core stack: `fastmcp>=2.0.0`, `pydantic>=2.5`, `python-frontmatter>=1.0`.

When in doubt:
- Re-read the model sections in the README and the key decisions + current state in `design.md` (treating the latter as internal development notes only).
- Review recent entries in `evolution.md` for context on why things are the way they are.
- Check `TRIAL.md` to understand what signals and evaluation criteria currently matter.
Ask clarifying questions rather than guessing invariants or skipping documentation updates.
