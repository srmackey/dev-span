# ContextForge — Design Summary

The snapshot of what ContextForge *is* — what was built vs. the original prompt
(Appendix A), the decisions that emerged during iteration, and where it currently
falls short. [evolution.md](evolution.md) is the running argument behind these
decisions; this file is the current-state snapshot. When the two disagree, this
file is current truth and the log explains how we got there.

## What stayed from the original prompt

- FastMCP server called ContextForge, local-first, stored under `~/.contextforge/`
- `uv` for deps, `contextforge` CLI entrypoint, stdio MCP
- SQLite for metadata + relationships
- README, `.env.example`, `mcp.json.example`
- Python 3.11+, typed, Pydantic models

## What changed, and why

| Initial | Built | Why |
|---|---|---|
| Licensing: "Apache-2.0 only" | Permissive / work-safe (MIT + Apache, no copyleft) | FastMCP/Pydantic are MIT — strict Apache-2.0 would have excluded the core stack. |
| Entity model: **Projects contain Tasks** | **Components + Repos + Tasks + Governance** (four peer entity types) | Real workflow is cross-repo. Components hold reusable facts; Repos hold codebase facts; Tasks compose them; Governance holds cross-cutting guidelines. |
| `contextforge-mcp/` nested dir | Files at workspace root | Workspace is already named `context-forge`; nesting was redundant. |
| Stack: FastMCP + **Chroma** + SQLite + files | FastMCP + **SQLite FTS5** + markdown files (no Chroma, no vectors) | For this corpus size, FTS beats semantic search on names/errors/paths. Three stores collapsed to two. Vectors deferred; revisit with `sqlite-vec` if FTS misses bite. |
| Stack deps: `chromadb`, `sqlite-utils`/`aiosqlite` | `python-frontmatter` + stdlib `sqlite3` | Chroma dropped. Sync `sqlite3` is plenty at this scale; fewer deps. |
| Storage: `projects/{project_key}/` + `chroma/` | Four entity dirs + `.index/contextforge.db` + `config.json` | Matches the peer-entity model. Markdown files are the source of truth; SQLite is rebuildable. |
| Resources: `context://project/{id}`, `context://project/{id}/task/{id}`, `context://search?q=` | `context://{component\|repo\|task\|governance}/{slug}`, `context://{type}/{slug}/{subtopic}`, `pack://task/{slug}` | Search is tool-only (actions fit tools better than resources). Pack uses `pack://` scheme to avoid colliding with `{type}/{slug}/{subtopic}`. |
| Tools: `build_or_update_task_context`, `add_cross_reference`, `semantic_search_across_context`, `list_related_entities` | ~30 single-purpose tools (see README) | Initial tool names were vague. Split into clear verbs. `get_task_pack` is the star — composes a task's full context bundle with governance cascade. |
| MCP Roots auto-detection | `bind_workspace` + `get_current_workspace` tools (client passes the path in) | Avoids a full Roots handshake while still letting the LLM resolve current workspace → repo → parent component. |
| "Consent descriptions for write tools" | Docstrings flag destructive ops (`delete_entity`, `delete_context`) | MCP clients surface docstrings; deeper consent gating not requested. |

## Key design decisions that emerged during iteration

### The three-then-four entity model

Started with Systems/Repos/Tasks as peers. Scenario exploration revealed:
- "System" was too narrow — it needed to cover internal subsystems, external services, APIs, databases, libraries, and third-party tools.
- Hierarchy exists: one "system" (the API gateway) can own multiple repos.
- Cross-cutting guidelines (security policy, user prefs, branding) apply across multiple entities and aren't cleanly owned by any one of them.

Resolution:
- Rename System → **Component**, with a `kind` enum: `system | service | api | database | library | tool`. (`system` is the generic fallback.)
- Repos get a `component:` parent field in frontmatter.
- Add a fourth entity type **Governance** for reusable guidelines, referenced (not owned) by other entities.

### Governance cascade

A task pack includes governance refs from:
1. The task itself (`governance: [...]` in task frontmatter)
2. Each linked component's governance
3. Each linked repo's governance
4. The parent component of each linked repo
5. `config.always_include` entries (optional global defaults)

All deduped.

### Aliases as first-class, globally unique

`component:api-gateway` may be known as "gateway", "gw", "the gateway", "edge-proxy". Aliases live in SQLite with a unique constraint; `resolve_ref` fuzzy-matches slugs + aliases + names and returns ranked candidates. Prevents the LLM from silently creating duplicates.

### Uses-graph + `suggest_task_links`

Components can declare `uses: [...]` outbound dep edges. `suggest_task_links` BFS-traverses from task anchors (default depth 3), scores candidates' subtopics via FTS against the task description, and returns top-K un-linked suggestions. Explicit linking stays; discovery is automated.

### Imported content via external MCPs

ContextForge does NOT fetch from Confluence/Jira/etc. Instead:
- `import_content(ref, content, source_url, source_name)` stores LLM-provided content as a subtopic with source tracking (`source_url`, `source_fetched_at`, `source_name` in frontmatter + SQLite).
- `refresh_source(ref)` returns the stored URL so the caller can re-fetch via another MCP (Atlassian, GitHub, etc.) and call `import_content` again.
- `list_stale_sources(older_than_iso)` surfaces batch-refresh candidates.
- Keeps ContextForge integration-agnostic; composition is the caller's job.

### External refs (not the same as imported content)

Tasks can carry `external_refs: [{system, id, url}]` — pointers to Jira tickets, GitHub PRs, etc. These are *references*, not stored content. Live state is fetched via a separate MCP when needed.

### User prefs: three layers, no new concept

- **Structured** (single-value): frontmatter fields on entities (`testing_framework: jest`).
- **Prose global**: a Governance entity (e.g. `governance:my-prefs`) added to `config.always_include`.
- **Prose entity-specific**: a conventional subtopic on the entity (e.g. `repo:ui-repo/style.md`).

## Ref grammar

```
type:slug               # entity-level ref
type:slug/subtopic      # one document within an entity
```

Types: `component | repo | task | governance`. Slugs/subtopics: lowercase `a-z0-9-`.

## File layout

```
~/.contextforge/
  components/{slug}/_meta.md, {subtopic}.md
  repos/{slug}/_meta.md, {subtopic}.md
  tasks/{slug}/_meta.md, {subtopic}.md
  governance/{slug}/_meta.md, {subtopic}.md
  .index/contextforge.db       # SQLite + FTS5, rebuildable via reindex
  config.json                  # always_include + workspaces
```

## SQLite schema (high level)

- `entities(type, slug, name, description, kind, component_parent, created_at, updated_at)`
- `aliases(alias PRIMARY KEY, entity_type, entity_slug)` — globally unique
- `subtopics(entity_type, entity_slug, subtopic, content, source_url, source_name, source_fetched_at, updated_at)`
- `task_links(task_slug, ref)`
- `governance_links(entity_type, entity_slug, governance_ref)`
- `uses_edges(from_component, to_component)` — component → component DAG
- `task_external_refs(task_slug, ext_system, ext_id, url)`
- `context_fts` — FTS5 virtual table over subtopic content

## Roadmap

The single home for forward-looking work. The doc split: this file is the actionable
index of *what's next*; [evolution.md](evolution.md) records *why* each item was
deferred, in the round that raised it. Ordered near-term first.

### Near-term priorities (trial-driven)

Per [TRIAL.md](TRIAL.md) — driven by observed friction, not anticipation (don't build on the first occurrence):

1. **Stress-test focus-mode** on a component with 15+ subtopics so the narrowing actually fires and `dropped` becomes observable.
2. **Use the governance cascade for real** — at least one Governance entity in `config.always_include` — to validate it against actual task packs.
3. **Exercise `tail_logs` + the persistent `logs/contextforge.log`** (Round 9) to replace manual trial notes with quantitative signals (pack frequency, dropped rates, governance hit rate, link vs suggest usage).
4. **Keep the TRIAL.md running log filled in** (the human "did it help?" layer on top of the machine logs).
5. **Test the session-distill loop** (Round 8) on 1–2 real tasks via [.cursor/rules/session-distill.mdc](../.cursor/rules/session-distill.mdc): capture a long session, restart cold from `get_task_pack`, and log whether it saved re-derivation. If it earns its keep, build the transient-subtopic FTS exclusion (deferred list below).

### Known limitations (current gaps)

Things ContextForge does **not** do today.

*Falls short of the real-world workflow:*
- **Workspace auto-detection is passive.** `bind_workspace` + `get_current_workspace` exist, but the LLM has to remember to call them with a path. No automatic "you're in `/path/to/ui-repo`, here's the repo context" prompt. Real Roots integration would help; client support across MCP clients is still uneven.
- **Unverified end-to-end MCP composition.** The Atlassian → `import_content` → `refresh_source` story is clean on paper, but two MCP servers haven't been composed yet to confirm the LLM orchestrates the round-trip without hand-holding.
- **Governance cascade unexercised.** The cascade primitive is built and tested, but `~/.contextforge/governance/` has been empty in real use so far. Until at least one real Governance entity is referenced from a task pack, it's unclear whether the design earns its keep or is over-engineered.
- **Big-component narrowing unexercised.** Focus-mode (`per_entity_top_k`, `min_score`, `dropped`) was built for components with many subtopics. Today every component has 4–5 — below the trigger threshold — so the lossy-pack mitigation hasn't fired against real data. Needs a 15+ subtopic stress test.

*Loses to peer tools:*
- **No rich editing UI.** Obsidian/Logseq have years of polish; you're stuck with VS Code + markdown.
- **No semantic / vector search.** Deliberate cut (see "Deliberately deferred" below). Will bite when the corpus grows or prose gets dense.
- **Single-user only.** No team share, presence, or sync service. Filesystem-as-truth supports git-synced shared markdown today; HTTP/SSE + multi-tenancy is the next step when git-sync stops being enough.
- **No proactive context surfacing.** The LLM must call tools; context isn't volunteered. Mitigated by the always-apply router rule (Round 10) but not eliminated — MCP is passive.
- **No temporal queries.** "What did I know about X last month" requires `git log` against `~/.contextforge/`, not a ContextForge primitive.
- **No auto-capture.** Mem0-style systems extract memories automatically; ContextForge requires explicit `upsert_context` / `import_content`.

### Deliberately deferred (by design)

Cuts made on purpose; each has a revisit trigger. Full rationale in the cited round.

- **Vector / semantic search via `sqlite-vec`** (not Chroma) — FTS5 beats embeddings for the dominant query shapes (names, paths, error strings). Revisit if `dropped` lists consistently miss the right subtopic, or at >1000 entries + dense prose + concrete missed queries. (Rounds 0, 2, 5)
- **HTTP/SSE transport + multi-tenancy** — needs auth, per-user/team scoping, migrations, audit. Earns its keep only when git-synced shared markdown stops being enough. (Rounds 0, 2)
- **Real Roots handshake** — `bind_workspace` is the chosen friction-killer; revisit when MCP-client Roots support is broadly adopted. (Round 2)
- **Background source refresh / daemon mode** — on-demand `import_content` + `list_stale_sources` is enough for v0; a scheduled-refresh daemon only if that proves too high-friction. (Round 4)
- **Transient subtopics excluded from FTS/focus** — so the session-distill `session-state` seed stops polluting the corpus. Deferred until the manual loop proves out (priority 5 above). Touches `storage.py` + `tools.py`. (Round 8)
- **Layer-B explicit subtopic pinning** — let callers pin subtopics that always survive narrowing, if the lexical heuristic proves too lossy. (Round 5)
- **Per-entity narrowing policy** — `narrowing_policy: always | never | auto` in frontmatter so an entity declares whether it should ever be narrowed. (Round 5)
- **Whole-pack token budget** — a global "most relevant N tokens across all linked entities" cap; needs a tokenizer dep the project has avoided. (Round 5)
- **`fetch_dropped(task_slug, ref)` tool** — make the dropped-recovery path one call; add once `dropped` is seen in practice. (Round 5)
- **Telemetry on narrowing hits/misses** — log included-vs-dropped per pack + which dropped refs the LLM later fetched, to tune `per_entity_top_k` / `min_score`. (Round 5)
- **Templates per component `kind`** — per-entity-type templates suffice; kind-specific is YAGNI.
- **Cloud DB / pluggable storage backends** — premature; filesystem-as-truth already supports git-sync for team share.

### Code-quality backlog

Project-quality gaps (not design decisions). Items already addressed are recorded in [evolution.md](evolution.md).

1. **Test coverage: storage done, tool/resource layer pending.** The storage engine is well covered (43 passing tests across entities, aliases, links, graph, delete, reindex, search, subtopics, taskpack — plus `refs` and `config`). Remaining gaps: `tools.py` (the MCP tool layer the LLM actually calls — arg handling, `dropped` surfacing, `get_current_workspace`), `resources.py` (`context://` / `pack://` handlers), and the ⚠️ `delete_entity` atomicity case in #2 (current delete tests are happy-path only). These are the next test targets.
2. ⚠️ **Sloppy transaction boundaries (data-integrity risk).** `delete_entity` commits multiple times; a crash mid-op could leave FS↔DB divergent. Wrap in explicit transactions.
3. **`storage.py` is large** (~1000+ lines), trending toward a god-class. Split into EntityStorage / LinkStorage / SearchStorage when next touched substantially.
4. **No migration story.** Schema changes break an existing `.index/contextforge.db`; `reindex` rebuilds the index but doesn't handle frontmatter schema changes.
5. **Alias uniqueness enforced at write but not at reindex.** Manual disk edits can create silent conflicts (`INSERT OR IGNORE` hides them).
6. **Loose dependency pins** (`>=`); `pyproject.toml` lacks classifiers and a proper license field.
7. **No CI, linting, or pre-commit hooks.**

---

## Appendix A — original build prompt

The historical seed this project grew from. Preserved verbatim; the tables above
record everything that changed between this prompt and what shipped.

```
You are an expert Python + FastMCP engineer. Create a complete, ready-to-run MCP server project for an AI context management system called ContextForge.

### Project Goals
- Local-first context manager for tasks, projects, and systems with powerful cross-referencing.
- All data stored in the user's home directory: ~/.contextforge/
- Use only Apache-2.0 licensed dependencies (work-safe).
- Support both stdio (local) and HTTP/SSE (future shared server).
- Use FastMCP (latest version) + Chroma (embedded vector DB) + SQLite (for metadata + simple relational cross-references).

### Project Structure to Create
contextforge-mcp/
├── pyproject.toml
├── README.md
├── src/contextforge/
│   ├── __init__.py
│   ├── server.py
│   ├── storage.py          # handles ~/.contextforge/ + SQLite + Chroma
│   ├── models.py           # Pydantic models for Task, Project, System, ContextEntry
│   └── resources.py        # MCP resources
│   └── tools.py            # MCP tools
├── .env.example
└── mcp.json.example

### Requirements
1. Use uv for dependency management.
2. In pyproject.toml: set up as a proper Python package with fastmcp, chromadb, pydantic, sqlite-utils (or aiosqlite), and any other minimal Apache-2.0 deps needed.
3. In src/contextforge/server.py: create a FastMCP instance named "ContextForge" with proper name/description.
4. Implement:
   - Resources (read context efficiently):
     - context://project/{project_id}
     - context://project/{project_id}/task/{task_id}
     - context://search?query={query}
   - Tools (AI actions):
     - build_or_update_task_context
     - add_cross_reference (links tasks ↔ projects ↔ systems)
     - semantic_search_across_context
     - list_related_entities
5. Storage in ~/.contextforge/:
   - projects/{project_key}/ (JSON + markdown files for raw context)
   - chroma/ (embedded Chroma collection per project)
   - contextforge.db (SQLite for metadata + relationships)
6. Auto-detect current workspace via MCP Roots.
7. Include clear consent descriptions for write tools.
8. Add a simple CLI entrypoint so `fastmcp run src/contextforge/server.py` works.

### After creating the files
- Provide the exact terminal commands to run:
  1. cd contextforge-mcp && uv sync
  2. fastmcp run src/contextforge/server.py
- Give an example mcp.json snippet for Cursor and Claude Code/Desktop.
- Add a short README with how to connect it in Cursor and how to test it.

Generate the full project now with high-quality, well-commented code. Use modern Python 3.11+ patterns. Make the code clean, typed, and production-ready for a prototype.
```
