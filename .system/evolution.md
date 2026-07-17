# ContextForge — Evolution Log

Running record of design decisions, the alternatives considered, and why each path was chosen or rejected. Append-only; supersede entries rather than rewriting them.

[design.md](design.md) is a snapshot of the *final* shape per round; this file is the running argument behind it. When the two disagree, design.md is current truth and this log explains why we got there.

---

## Round 0 — Initial coaching review (pre-build)

User submitted the original build prompt (preserved as Appendix A in [design.md](design.md)) — an MCP context management system spec — and asked for pressure-testing before building.

### What is a "ContextEntry"?

The original spec listed a `ContextEntry` model but never defined its shape. Considered three possibilities:
- Free-form markdown note with tags.
- Structured log (decision, observation, blocker, TIL).
- Zettelkasten-style atomic card.

**Recommendation at the time:** minimal `{id, kind, title, body_md, tags[], created_at, links[]}` with a soft-enum `kind`. **Outcome:** rendered moot by the entity-model pivot in Round 1 — the question stopped being "what is an entry" and became "what entity does this belong to."

### Licensing: "Apache-2.0 only"

The original spec said Apache-2.0 only. Flagged as inconsistent with the proposed stack: FastMCP, Pydantic, and aiosqlite are MIT. Three options:
- Hold strict Apache-2.0 → rebuild against an Apache-2.0-only stack (large surface to replace).
- Permissive / work-safe / no copyleft (the actual likely intent).
- Re-derive constraint from policy rather than guess.

**Decision:** "permissive, work-safe, no copyleft." Confirmed explicitly by user.

### Three data stores

The spec proposed SQLite + Chroma + JSON/markdown files on disk — three stores with no transaction boundary. Two collapse paths considered:
- **SQLite-only + `sqlite-vec`** — one file, ACID, trivial backup. Rejected for v0 because vectors weren't yet justified for the workload.
- **Markdown-on-disk + SQLite index** — filesystem is source of truth, SQLite is a derived cache. **Chosen** because it plays well with git, grep, and human editing, and the requirement to "view/edit/delete at will" maps naturally to opening a `.md` file.

Chroma dropped entirely. Note: it earns its keep around ~10k entries; we're well under that.

### Search: semantic vs lexical

Considered:
- **Pure semantic** (Chroma + embeddings) — rejected: weaker than FTS for the dominant query types in the use cases (function names, endpoint paths, error strings, service names).
- **Hybrid FTS + vectors with reciprocal ranking** — viable but complexity not yet justified.
- **FTS5 only** — chosen for v0. Re-evaluate when corpus grows or prose density bites.

### v0 scope cuts

- Defer HTTP/SSE → stdio only. Reason: HTTP brings auth + multi-tenancy.
- Defer `add_cross_reference` as a tool → use inline `[[wiki]]` parsed on write. Reason: explicit cross-ref tools tend to go unused by LLMs. (Later overridden — explicit `link_task` ended up being central; inline-only would have hidden the structural edges from SQLite.)
- Defer per-project Chroma collections → moot once Chroma was dropped.

### Tool naming

Original tool names (`build_or_update_task_context`, `add_cross_reference`, `semantic_search_across_context`, `list_related_entities`) were vague. MCP clients pick tools by name + description, so vagueness is a real cost. Decision: split into single-purpose verbs (`capture_context`, `recall_context`, `link_context`, plus the boring ones LLMs reach for: `list_*`, `delete_*`, `get_recent`).

### MCP Roots for workspace detection

Original spec relied on Roots. Flagged that client support is uneven (Claude Desktop yes, others patchy). Need a fallback. Decision deferred — see Round 2.

---

## Round 1 — Use-case-driven entity model

User described real workflows:
- New UI feature calling serviceA → wants serviceA's relevant interaction context plus UI repo's style/testing context.
- Bug fix spanning UI + DB + API repos → needs trace context across all three.
- New feature set adding pages + endpoints + DB scripts + DAOs → cross-repo composition.

### Pivot: from one ContextEntry to three peer entity types

The use cases are not "AI context management" in the abstract — they're "compose per-task context packs from reusable system + project facts." That reframing led to:

- **Systems** (long-lived facts about external services, APIs, etc.)
- **Projects/Repos** (long-lived facts about codebases — style, testing, layout)
- **Tasks** (transient, reference N systems + M repos + own notes)

Killer operation: assemble the pack for task T. The thing no existing tool does well — and what every use case needed.

### Storage layout

Considered:
- **Project-local `.contextforge/` in each repo** — better for team share, but context travels with branches (sometimes weird, sometimes wrong).
- **Global `~/.contextforge/`** — single source of truth, simpler, no per-repo bootstrapping.

User picked global for now. Note left to revisit when team-sharing becomes real.

### Task pack assembly

Two shapes considered:
- **Full dump** of all linked system/project notes — simpler, balloons context for big systems.
- **Explicit subtopic refs** (`serviceA/auth`, not all of `serviceA`) — scales better, more linking work upfront.

**User chose explicit subtopic refs.** This decision is the seed of Round 4's "scoped pulls" problem: even with explicit refs available, entity-level refs (`component:api-gateway`) still resolve to *all* subtopics, which is what bit later.

### Reference grammar

Locked: `type:slug` for entity-level, `type:slug/subtopic` for one document. Types `system | repo | task` (later expanded to four).

### Tool surface (initial)

13 single-purpose tools across entity management, context CRUD, task composition, and search. Notable:
- `pack://task/{slug}` resource scheme separate from `context://` — to avoid collision with the `{subtopic}` slot in `context://{type}/{slug}/{subtopic}`. Without the separate scheme, `context://task/foo/pack` would be ambiguous (is "pack" a subtopic?).

### Things rejected at this round

- Project-local `.contextforge/` (revisit when sharing).
- Vector search (defer until FTS misses bite).
- HTTP/SSE.
- Auto-Roots integration.

---

## Round 2 — Post-build evaluation: four suggestions

User proposed four enhancements after the initial build. Each evaluated:

### 1. Optional vector backend

**Decision: defer.** Reasoning: FTS5 is *better* than embeddings for the dominant query shapes (function names, endpoint paths, error strings, service names). Trigger to revisit: >1000 entries + real prose content (postmortems, design docs) *and* concrete missed queries to point at.

If/when added: use `sqlite-vec` (Apache-2.0, ~200KB extension, stays in SQLite), **not Chroma** — re-adding Chroma brings back the dep weight just cut.

### 2. `pack://` as a resource

**Already done** in [resources.py](../src/contextforge/resources.py). Documented the *why* of the separate scheme (collision avoidance, see Round 1).

### 3. Roots auto-detection

**Valuable but needed a design decision first.** Roots tells you the workspace path; it doesn't tell you which repo slug that path maps to. Three options:
- **(a) Slugify directory basename** — zero friction, but breaks when directory names don't match canonical slugs (`my-fork-of-ui-repo` ≠ `ui-repo`). Silent ambiguity.
- **(b) Explicit user-configured map** in `~/.contextforge/config.toml` — deterministic, but requires editing config files.
- **(c) `bind_workspace(repo_slug)` tool** — one prompt of friction on first use, remembered forever, zero ambiguity. **Chosen.**

Real Roots handshake (capability negotiation with the MCP client) was deferred separately because client support is uneven. Tools accept a path arg; client supplies it.

### 4. Pluggable storage backends

**Decision: actively don't.** Classic premature-abstraction trap. Reasons:
- Interfaces leak the dominant backend's assumptions; the "pluggable" promise breaks the moment backend #2 lands.
- The real shared-server path is "run ContextForge against a shared filesystem" (git-synced markdown, S3-FUSE, NFS) — the current filesystem-as-truth design *already supports that* without abstraction.
- Cloud DB would need different data shapes anyway (user IDs, ACLs, audit) — better to do a real migration when the need is concrete.

Ranking the four: #3 > #2 (already done) > #1 (defer, sqlite-vec not Chroma) > #4 (actively don't).

---

## Round 3 — Hierarchy, aliases, and the four-entity model

User scenario: project touching four repos belonging to three "systems" (UI, API, GATEWAY), with the gateway owning two repos. Repos called by aliases ("proxy", "gw", "edge-proxy"). Cross-cutting concerns (identity, auth, branding, company expectations) apply to all.

### Two structural gaps surfaced

**1. System → Repo hierarchy is real and missing.** In the prior model Systems and Repos were peers; the scenario showed 1-to-many containment.

**2. Aliases are core, not a nice-to-have.** Without first-class aliases, either users type exact slugs (friction) or the LLM guesses and creates duplicates (drift).

### Hierarchy traversal in task packs

When a task links `repo:ui-repo`, should the pack also include the parent system?
- **(a) Implicit (parents-by-default)** — power move, risks context bloat. Initially leaned this way.
- **(b) Explicit** — safer, more verbose.

Outcome: explicit linking stayed as the rule; the **governance cascade** (Round 4 below) became the structured way to pull parent context without making *every* parent-link implicit. Avoids the bloat trap while still solving "I'm in proxy-repo, gateway context matters too."

### Cross-cutting "company/org" context

Three shapes considered:
- **(a) Reserved top-level entity** like `org:acme` — clean, schema change.
- **(b) Conventional system** like `system:org` — no schema change, just a convention.
- **(c) Global `~/.contextforge/_org/`** always implicitly prepended — magic, hard to reason about.

Initial recommendation: **(b)**. User pushed back: wanted these as **top-level entities other entities can reference, not implicitly prepended, with overlapping subsets per entity**. That feedback drove the **Governance entity type** decision in Round 4 — option (a) effectively, but generalized to "any reusable guideline" rather than just org.

### User preferences

Three shapes:
- **(a) Reserved subtopic name** (convention, e.g. `_prefs.md` on any entity).
- **(b) Separate `prefs://` entity type** and resource scheme.
- **(c) Frontmatter only** (small structured prefs like `testing_framework: jest`).

**Chosen: hybrid of (a) and (c).** Structured single-value prefs in frontmatter; prose prefs in conventional subtopics (`style.md`). Round 4 added a third layer for global prose prefs — see Governance below.

### Alias conflict policy

Three options:
- **(a) Reject at write-time** (globally unique across all aliases + slugs + names). **Chosen.**
- (b) Allow ambiguous, return ranked candidates from `resolve_ref`.
- (c) Scope per entity type (`gw` could mean different things in system-space vs repo-space).

Reason for (a): matches how humans actually use shorthand — you don't say "gw" meaning two different things in the same conversation. Simpler to reason about; collisions are loud, not silent.

---

## Round 4 — Generalization, third-party tooling, scoped pulls

User raised three more points:
1. External services, libraries, etc. need first-class representation.
2. Third-party tooling (Jira, GitLab, GitHub, CI/CD) provides context — how to integrate?
3. Scoped pulls: scenario where a task touches only part of multiple systems.

### Generalize "System" with a `kind` field

Considered:
- **Add three new entity types** (Library, Database, Tool, etc.) — multiplies tool surface (`create_library`, `create_database`, ...) and LLM confusion.
- **One bucket with a `kind` enum** — `system | service | api | database | library | tool`. **Chosen.** Same shape (meta + subtopics + aliases + relations); differences are templating concerns, not schema concerns.

Initial proposal had `kind: internal | external | api | database | library | tool`. User pushed back on `internal/external` and asked for `system` and `service`. Final enum: `system | service | api | database | library | tool` (with `system` as the generic fallback).

### Third-party tooling: reference, don't mirror

Two paths considered:
- **Cache live ticket/PR/CI state inside ContextForge** — rejected: it rots; ContextForge becomes a ticket client.
- **Store references and process descriptions; fetch is another MCP's job** — chosen.

Concretely: ContextForge stores `external_refs: [{system, id, url}]` on tasks (pointers, not content) plus a `system:jira` entity describing *how the team uses Jira* (process docs). Live state is fetched by a separate MCP server alongside ContextForge.

### Background scouring of Confluence: rejected

User asked about background tasks that scour Confluence/Atlassian for signal. **Rejected as a trap:**
- v0 is a stdio MCP server — no long-running process, no scheduler. Background mode would require a daemon.
- Background scouring would fetch *every* page, not the relevant ones. Solving relevance is harder than solving fetch.
- The cleaner shape: explicit `import_content(ref, content, source_url, source_name)` — LLM fetches via Atlassian MCP, calls ContextForge to store. Plus `refresh_source(ref)` returns the URL so the LLM can re-fetch. Plus `list_stale_sources(older_than)` for batch-refresh on demand.

ContextForge stays integration-agnostic; composition is the caller's job. Layer a daemon mode later if needed.

### Scoped pulls: graph + FTS relevance (initial cut)

Built two primitives:
- **`uses: [...]` outbound dep edges** on Components — optional, rots if ignored, useful when maintained.
- **`suggest_task_links` tool** — BFS over the uses-graph from anchors (default depth 3, user requested min 3 configurable), FTS-scores candidates' subtopics against the task description, returns top-K ranked suggestions.

This solves *discovery* of relevant subtopics. It does **not** solve narrowing at pack-assembly time — that's the gap revisited in Round 5.

### Templates

User: templates per **entity type** (Component / Repo / Task / Governance), **not per `kind`**. Per-kind would have been YAGNI; per-entity-type lowers cold-start cost without a combinatorial explosion.

Stub templates:
- Component → `overview.md`, `auth.md`, `integration.md`, `gotchas.md`
- Repo → `overview.md`, `style.md`, `testing.md`, `local-dev.md`
- Task → `goal.md`, `plan.md`, `notes.md`
- Governance → minimal stub

### Governance: from flag to entity type

Initial proposal: `governance: true` flag on Component frontmatter, marked components auto-included in every pack. **User rejected**: wanted reusable guideline entities that other entities reference, with different overlapping subsets per entity.

**Final shape:** new entity type `Governance`, refs as `governance:<slug>`. Any other entity references applicable governance via `governance: [slugs]` in frontmatter. Task pack unions governance from: the task itself + each linked component + each linked repo + parent components of linked repos. Deduped.

This also gave the third layer of user prefs:
- **General prose prefs**: a Governance entity (`governance:my-prefs`) added to `config.always_include`. Auto-pulled into every pack.
- **Specific prose prefs**: a conventional subtopic on the relevant entity (`repo:ui-repo/style.md`).
- **Structured prefs**: frontmatter fields (`testing_framework: jest`).

Three layers, all reusing existing primitives — no new concept.

### Naming nit: `kind: system` vs renaming the entity

The recursion `kind: system` on entity-type System reads weird in docs. Three options:
- Keep as-is (minor awkwardness in conversation, clean in data).
- Rename the fallback kind to `service` or `generic`.
- Rename the entity type from "System" to something neutral.

User chose: **rename the entity type** to **Component**. `kind: system` stays as the generic fallback. Repo's parent field becomes `component:` (was `system:`). This was a bigger refactor than keeping the name, but eliminates the recursion permanently.

Briefly considered alternative names: `Source`, `Component`. `Component` won.

---

## Round 5 — Scoped pulls (the lossy-pack problem)

User: linking entity-level refs pulls all subtopics. Need to tighten.

This is the gap the "Known limitations" section of [design.md](design.md) flagged after the post-build evaluation, now being addressed.

### Problem

[`get_task_pack`](../src/contextforge/storage.py#L611) calls [`_resolve_ref_content`](../src/contextforge/storage.py#L661), which returns *every* subtopic of an entity-level ref. Same applies to governance entities gathered through the cascade. Big components balloon the pack.

`suggest_task_links` already returns subtopic-level refs (good), but most existing links and `config.always_include` entries are entity-level (rotten by the time the pack is assembled).

### Options considered

#### Option A — FTS-narrowed entity refs (heuristic filter)

Keep entity-level link semantics. At pack-assembly, when a ref is entity-level and the entity has more than K subtopics, FTS-rank the entity's subtopics against a query built from the task description + own subtopics, concat top-K. Always include `_meta` description. Return a `dropped: list[str]` so the LLM can request more.

Pros:
- Backwards compatible — existing entity-level links keep working.
- Zero extra effort per task.
- `suggest_task_links` and the uses-graph stay coherent (entity-granularity).
- Reversible per call (`focus=False`).

Cons:
- Heuristic. FTS is lexical; conceptually-relevant-but-lexically-distant subtopics can rank low. Mitigated by `dropped` + tunable `top_k`/`min_score`.
- Adds knobs.
- Two retrieval modes to test.

#### Option B — Subtopic-only links (explicit selection)

Drop entity-level link semantics. Links must be subtopic-level. Whole-component pulls require enumerating subtopics.

Pros:
- Deterministic and obvious. No ranking, no surprises.
- Simpler `_resolve_ref_content`.
- Forces precision at link time.

Cons:
- Higher upfront cost per task; more `list_subtopics` calls and more chances to miss one.
- Breaks existing data — every entity-level link in tasks needs migration; `config.always_include` semantics change.
- Governance cascade gets awkward — gathered automatically from linked entities; need a rule for *which* governance subtopics cascade. Either cascade all (back to the original problem), or require governance entities to be small.
- `suggest_task_links` becomes the *only* discovery path, so its quality bar goes up.

#### Comparison

| Axis | A: FTS-narrowed | B: Subtopic-only |
|---|---|---|
| Pack precision | Good, sometimes wrong | Exact |
| Linking cost | Low | High (enumerate) |
| Backwards compat | Yes | Migration needed |
| Failure mode | Silent omission (mitigated by `dropped`) | Silent omission if LLM forgets a subtopic |
| Governance cascade | Works, also gets narrowed | Needs a new rule |
| Code complexity | One new branch + ranking | Simpler core, awkward cascade |
| Recoverability | `focus=False` toggles off | Hard to undo data migration |

### Decision: Option A

Reasoning:
- A's failure mode (subtopic ranked below cutoff but visible in `dropped`) is *easier* to detect than B's (LLM forgets to link a subtopic — silent and invisible).
- A preserves the entity-level model that `suggest_task_links` and the uses-graph already depend on.
- A is reversible per call (`focus=False`); B is a one-way data migration.
- B can still be layered on top of A later if A proves insufficient; the inverse is harder.

### Implementation shape

- `get_task_pack(slug, *, focus: bool = True, per_entity_top_k: int = 3, min_score: float | None = None)`.
- `_resolve_ref_content` gains an optional `query` arg. When `focus=True` and the ref is entity-level with more than `per_entity_top_k` subtopics, FTS-rank the entity's subtopics against the query and concat top-K. Otherwise unchanged.
- `_meta.description` is always included as the entity overview, regardless of ranking.
- Subtopic-level refs (`component:api-gateway/auth`) bypass narrowing — explicit selection wins.
- Same narrowing applies to cascaded governance refs ([storage.py:625-636](../src/contextforge/storage.py#L625-L636)).
- `TaskPack` model in [models.py:76](../src/contextforge/models.py#L76) gains `dropped: list[str]` so the LLM can pull on demand.

---

## Forward-looking items → see design.md → Roadmap

Open/deferred work and the code-quality backlog are consolidated into a single
roadmap in [design.md](design.md) ("## Roadmap"), per the doc split: this log is
*what changed and why* (append-only); design.md is *current state + roadmap*. The
*why* behind each deferral lives in the round that raised it — narrowing follow-ons
(Layer-B pinning, sqlite-vec ranking, per-entity policy, token budget, `fetch_dropped`,
telemetry): Round 5; Roots handshake: Round 2; daemon-mode refresh: Round 4; HTTP/SSE
+ vectors: Rounds 0/2; transient-subtopic FTS exclusion: Round 8.

**Already addressed (changelog):** tools-reached-into-storage-internals → public
`get_repo_component()` (post-PR #1); naïve phrase-only FTS → `_fts_or_query` for the
focus path (Round 5; the general `search` tool is still phrase-only); logging (Round 6).

---

## Round 6 — Logging

### Problem

No visibility into pack assembly behaviour: couldn't tell whether narrowing fired, which subtopics were selected vs dropped, or how long assembly took. Debugging and tuning `per_entity_top_k` / `min_score` was fully blind.

### Design decisions

**stderr only, no log file.** MCP stdio uses stdout for the protocol; stderr is safe. A rotating file handler would add complexity with little benefit — `CONTEXTFORGE_LOG_LEVEL=DEBUG` redirected to a file is enough for offline analysis.

**Two-level strategy: INFO for operations, DEBUG for optimization signal.** INFO is the default so production use isn't noisy. DEBUG is opt-in and captures the full FTS scoring breakdown needed to tune the narrowing system.

**Fetch all FTS matches (no LIMIT) inside `_resolve_ref_content`.** Previously only `top_k` rows were fetched, so scores for dropped-but-matched subtopics were invisible. Fetching all matches and splitting post-fetch lets us log scores for every subtopic — selected, dropped-low-score, and no-match — at negligible cost given typical subtopic counts.

### Log events

| Level | Event | Key fields |
|---|---|---|
| `INFO` | `pack:start` | task, link count, focus on/off, query term count, top_k |
| `INFO` | `pack:done` | task, linked/governance counts, total dropped, total chars, elapsed ms |
| `DEBUG` | `resolve:narrowed` | ref, subtopics before→after, score per selected subtopic, score per dropped-but-matched subtopic, list of no-match subtopics |
| `DEBUG` | `resolve:no_signal` | ref, subtopic count — fires when FTS returns zero hits and full-content fallback activates |
| `ERROR` | `resolve:missing_entity` / `resolve:missing_subtopic` | ref |
| `WARNING` | `pack:bad_always_include` / `pack:bad_governance_ref` | unparseable ref string, task slug |

### Optimization use

The `resolve:narrowed` DEBUG line is the primary optimization signal. It shows exactly which subtopics scored what, making it possible to:
- Identify subtopics that are structurally relevant but consistently score near zero (signal that `_fts_or_query` terms aren't matching the subtopic's vocabulary — candidate for a synonym/alias fix or a `min_score` threshold adjustment).
- Confirm that `per_entity_top_k` is set appropriately: if the selected set keeps including scaffold stubs (score near zero) instead of real content, raising `top_k` or dropping `min_score` to a hard floor would help.
- Spot the `resolve:no_signal` fallback as a sign that a task's description is too sparse to drive narrowing.

---

## Round 7 — First-time setup; SQLite under FastMCP threads

Not a design round so much as a record of what real first-time install surfaced. Captured here so the load-bearing decisions and recurring corporate-network gotchas don't get lost.

### Problem

After wiring the server into Cursor on a corporate macOS laptop, all SQLite-backed tools (`list_components`, `list_repos`, `search`, …) failed on first call with:

```
SQLite objects created in a thread can only be used in that same thread.
The object was created in thread id X and this is thread id Y.
```

Config-only tools (`get_config`, `get_current_workspace`) worked fine, which localized the bug to the storage layer.

### Cause

`Storage` opened a single `sqlite3` connection at server startup. FastMCP dispatches tool calls on different worker threads; `sqlite3.Connection` defaults to `check_same_thread=True` and refuses cross-thread use.

### Options considered

- **(a) `sqlite3.connect(path, check_same_thread=False)`.** One connection shared across threads. Silences the error but still serializes all calls through one connection and relies on Python's GIL + SQLite's own locking for safety. Cheap, but worse concurrency under load.
- **(b) `threading.local()` — one connection per thread.** Each worker gets its own connection, opened lazily on first use. Pair with `PRAGMA journal_mode=WAL` so multiple connections can read concurrently with writers. Slightly more code; better behaviour under concurrent reads.
- **(c) Connection pool.** Overkill for a stdio MCP server with single-digit concurrency.

**Chosen: (b).** Per-thread connections via `self._local = threading.local()`, lazy `_connect()`, WAL pragma on every fresh connection, and `close()` only closes the calling thread's connection. See [storage.py:152](../src/contextforge/storage.py#L152), [storage.py:160-166](../src/contextforge/storage.py#L160-L166), [storage.py:1069-1072](../src/contextforge/storage.py#L1069-L1072).

This makes the threading model load-bearing: future refactors must keep `Storage` accessed only via its public API and must not cache a `Connection` on the instance. Removing WAL would break concurrent-reader semantics that the design now assumes.

### Corporate-network setup gotchas

Issues that aren't bugs in ContextForge but are guaranteed to recur on any corporate macOS setup behind an SSL-inspecting proxy:

- **`uv` not preinstalled.** Install via `brew install uv` or Astral's installer:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
  Alternative without uv: `python3 -m venv .venv && pip install -e .` and point Cursor MCP at `.venv/bin/contextforge` instead of `uv run`.

- **`uv sync` fails with `invalid peer certificate: UnknownIssuer`.** uv ships its own CA bundle; a corporate SSL-inspecting proxy presents a corporate cert that lives in the macOS keychain but not in uv's bundled trust store. The error is verbatim:
  ```
  × Failed to fetch: `https://pypi.org/simple/<pkg>/`
  ╰─▶ invalid peer certificate: UnknownIssuer
  help: Consider enabling use of system TLS certificates with the
       `--system-certs` command-line flag
  ```
  Fixes (one-off): `uv sync --system-certs`. Persistent — pick one:
  ```bash
  export UV_SYSTEM_CERTS=1                              # add to ~/.zshrc
  # or
  mkdir -p ~/.config/uv && echo 'system-certs = true' >> ~/.config/uv/uv.toml
  ```
  Mirror the flag in `.cursor/mcp.json` args (or set `UV_SYSTEM_CERTS=1` on the server entry's `env`).

- **Nexus 403 / quarantine ≠ TLS.** A quarantine 403 from a corporate Nexus mirror is supply-chain *policy*, not a flaky cert. Do **not** "fix" it by switching to public PyPI. The mirror URL (informational only — not required for ContextForge install once `--system-certs` is on) takes the form:
  ```
  UV_INDEX_URL=https://nexus.internal.example:8443/nexus/repository/pypi-all/simple
  ```

### Global Cursor install (mcp-manager proxy mode)

Project-scoped `.cursor/mcp.json` is documented in README. For machines using an `mcp-manager`-style proxy (`~/.cursor/mcp-proxy-config.json`), the equivalent backend entry is:

```json
"contextforge": {
  "command": "uv",
  "args": [
    "--system-certs",
    "run",
    "--directory",
    "/ABSOLUTE/PATH/TO/context-forge",
    "contextforge"
  ],
  "env": {
    "CONTEXTFORGE_LOG_LEVEL": "DEBUG"
  }
}
```

After editing the proxy config no Cursor reload is required; mcp-manager picks up the change.

### Smoke test (verified 2026-06-22)

Seven-step smoke test from README ran end-to-end successfully on the fixed setup:

1. `create_component(slug="api-gateway", kind="system", ...)`
2. `upsert_context(ref="component:api-gateway/auth", ...)`
3. `create_governance(slug="security-policy", ...)`
4. `add_governance(ref="component:api-gateway", governance_ref="governance:security-policy")`
5. `create_task(slug="demo-task", ...)`
6. `link_task(task_slug="demo-task", refs=["component:api-gateway/auth"])`
7. `get_task_pack(task_slug="demo-task")` — returned linked auth subtopic + cascaded `governance:security-policy` (scaffolded `overview` + `rules` subtopics); `dropped=[]`.

### Trial decision baseline

The threading fix is what made the 2026-06-22 trial start at all. If a future run loses the WAL pragma or per-thread connection model and the `SQLite objects created in a thread…` error returns, that's the regression to look for first.

---

## Round 8 — Session distillation / handoff loop (2026-06-23)

### Problem

Long real-world work sessions (day-job Jira tasks) bloat context and sometimes need a fresh start mid-task. ContextForge captures *durable* task knowledge well, but it was not capturing *in-flight, unfinished* working state — so a cold restart lost momentum.

### Key insight: two outputs, opposite filters

The "dead-end test" settled it. A path you tried and ruled out this session:
- **fails** the durable-corpus filter ("would a cold agent on a future unrelated task want this?") → it's noise in the corpus, and FTS/focus would treat it as signal;
- **passes** the resume filter ("what do I need to pick this up tomorrow?") → it stops you re-exploring a dead path.

So the corpus cannot subsume the resume seed; they need different homes:
- **Session seed** (transient, overwrite) → `task:<slug>/session-state`. Holds status, next step, open loops, dead-ends, working hypothesis.
- **Durable distillation** (append, permanent) → `task:<slug>/journal` (decision/rationale trail — this log at task scale) + notes/implementation-notes for gotchas.

### Decision

Implement first as a manually-invoked Cursor rule — [.cursor/rules/session-distill.mdc](../.cursor/rules/session-distill.mdc) — that drives the distillation via existing tools (`upsert_context`, `append_context`, `get_task_pack`). **No server change**, deliberately: prove the loop earns its keep on a couple of real tasks (per the TRIAL.md ethos) before changing pack assembly. Rejected a separate `.handoff/` mechanism — it would compete with the Task entity and split state across two stores.

### ⚠️ Deferred — revisit when the loop is proven

`session-state` is *meant* to be transient but currently lands in the searchable corpus like any subtopic, so it pollutes FTS and inflates packs. **When the manual loop demonstrably helps** (logged in TRIAL.md), build the exclusion: mark transient subtopics (leading-underscore convention or a `transient: true` frontmatter flag) and skip them in FTS indexing + focus narrowing, while still including them in `get_task_pack`. This touches `storage.py` (index/schema) and `tools.py` (pack assembly). Until then, keep `session-state` short and overwrite-only.

---

## Round 9 — Persistent usage logging for evidence (2026-06-23)

### Problem

The trial (TRIAL.md) and design evaluation (design.md) depend on visibility into real behavior:
- How often is `get_task_pack` called with `focus=True` and what `dropped` counts/sizes result?
- Is the governance cascade ever exercised outside the smoke test?
- How frequently do people use `suggest_task_links` vs. manual `link_task`?
- Do `resolve_ref` and workspace binding actually get used in flow?
- Are entities being maintained (upserts) or created and abandoned?

Current logging (Round 6) was stderr-only. Users had to set `CONTEXTFORGE_LOG_LEVEL` and arrange redirection in their MCP client config (Cursor logs, etc.). This made passive collection during ordinary work unreliable. The "keep the log" instruction in TRIAL.md was almost entirely manual.

### Decision

Add **persistent, rotating file logging by default** inside the storage root:

- `~/.contextforge/logs/contextforge.log` (RotatingFileHandler, 5 MB × 3 backups).
- Same structured `key=value` format already used for pack:start/done etc.
- Setup happens automatically in `Storage.__init__` (after `_init_dirs`), so every home gets it.
- Stderr handler (live debugging) unchanged.
- New `tail_logs(n)` tool surfaces recent lines directly via MCP (no fs poking required for the agent).
- Added INFO-level events for: entity creates, task link/unlink, governance attach/remove, external refs, always_include changes, workspace bind/unbind, resolve_ref, suggest_task_links, context upsert/append/delete.

`CONTEXTFORGE_LOG_LEVEL=DEBUG` still works for both streams (detailed FTS narrowing scores).

No new dependencies. Logging is best-effort; failures to write the log file never affect core operations.

### Rationale vs. prior "no file log" stance

Round 6 explicitly chose stderr-only because "a rotating file handler would add complexity with little benefit." The benefit is now concrete and repeated: the trial cannot answer its own success criteria (governance exercised? focus triggered? autonomous value?) without reliable capture of pack and link activity. Persistent logs are the instrumentation the TRIAL.md rubric asked for, implemented in the system itself rather than left to the operator.

This is observability for the existing model, not a new user-facing feature. It directly supports the "evidence-based evolution" rule in AGENTS.md.

### Follow-ups recorded

- Update TRIAL.md "How to instrument" section (now points at the on-disk log + `tail_logs`).
- Update README smoke test / maintenance section and design.md known limitations if needed.
- Future: a `get_usage_summary()` tool that parses the log for aggregates (packs/day, avg dropped, governance hit rate) would be a small follow-on once we have data.

### Code touch points

- storage.py: `_ensure_persistent_log_handler`, calls from `__init__`, `logs/` dir, new `tail_logs`, many new `logger.info` calls.
- config.py: light logging on always_include and workspace changes.
- tools.py: `tail_logs` wrapper.
- server.py: improved docstring + INSTRUCTIONS mention of logs.
- .system/ docs updated here; README to follow.

The change is intentionally small and reversible (delete the logs/ dir or raise log level).

### Follow-up: repo-traveling logs for cross-machine evaluation (2026-06-23)

After the initial implementation, the need arose to have the usage events live *inside this repository* rather than (or in addition to) `~/.contextforge/`.

Goal: when dogfooding ContextForge while working on ContextForge itself, the captured `pack:*`, link, governance, focus, etc. data should be easy to inspect "at home" or on another machine without copying files out of a home directory.

**Solution chosen:**
- Added `setup_extra_logging()` + support for the `CONTEXTFORGE_LOG_FILE` environment variable.
- When set, the exact same events are appended to *both* the normal home log **and** the path given in the variable ("both places for a while").
- No code in the runtime ever references `.system/`. The path is supplied entirely by the developer via env (or their `.cursor/mcp.json` for this workspace).
- Created `.system/usage-logs/` (with README) + gitignore rules for `*.log` files inside it.
- The directory + README travel with the repo; the actual log content can be force-added when you want to preserve a particular trial run as evidence.

**How to use while working here:**
```bash
export CONTEXTFORGE_LOG_FILE="$(pwd)/.system/usage-logs/contextforge.log"
export CONTEXTFORGE_LOG_LEVEL=INFO
uv run contextforge
```

Or set the same in the project-local mcp.json under `env`.

This satisfies the request to have logs that "travel in the repo" while preserving the correct separation for end-user installations.

Also updated:
- .system/usage-logs/README.md (detailed instructions)
- .gitignore (ignores the logs but the structure travels)
- evolution + TRIAL docs as needed.

This is a development workflow aid, not a change to the product's logging model.

---

## Round 10 — Global install + proactive invocation (2026-06-23)

### Problem

Two friction points surfaced in real cross-repo use:
1. Wiring felt like it required adding the context-forge folder to every workspace.
2. ContextForge wasn't being used organically — the user had to explicitly prompt
   "add this to ContextForge" / "did you check ContextForge?" for it to happen.

### Shared root cause

Both stem from **project-scoped wiring for a global-by-design tool.** Data lives in
`~/.contextforge/` and is meant for every repo, but the MCP registration and the
`.cursor/rules/` live inside this repo. The `--directory` arg only points `uv` at the
*code*; the server reads `~/.contextforge/` regardless of open workspace — so the
folder never needs to be in another workspace. The fix is to install both the server
and the router rule **globally.**

### Why "not organic" persisted even with the rule symlinked globally

The user had already symlinked `contextforge-router.mdc` into the global config, yet
behavior was still non-proactive. Two reasons:
- The rule was `alwaysApply: false` → an *Agent-Requested* rule, so Cursor's model
  decided per-request whether to attach it. At ticket-mention time it often judged
  the rule irrelevant, so the guidance wasn't in context and nothing fired.
- The capture/lifecycle guidance was soft — no concrete trigger to *create* a task on
  ticket mention; both of the user's examples were capture-side.

### Decision

- Flip the router to **`alwaysApply: true`** so it's always in context (removes the
  model's discretion about *loading* it). `session-distill.mdc` stays manual.
- Add **explicit, pattern-based triggers**: ticket pattern `[A-Z]+-\d+` → `resolve_ref`,
  then `get_task_pack` or `create_task` + `link_task`; and "recall aggressively,
  capture at checkpoints" (auto-recall is safe; auto-capture is gated to decisions/
  workarounds/wrap-up to avoid writing junk).
- README rewritten to make **global install the default**, kill the workspace-folder
  misconception, and document the router rule going global via **symlink or copy**
  (either/or; symlink = single source of truth, copy = more portable, Windows
  symlinks need Developer Mode).

### Honest ceiling

MCP is passive — no server push. This is instruction + model adherence only. Expect
"mostly automatic with the occasional nudge," not perfect. This mitigates the
documented "No proactive context surfacing" gap rather than closing it.

---

## Round 8 — Adding the first test suite (2026-06)

### Motivation
"no test suite exists yet" in the project instructions. Adding tests improves confidence for future evolution and catches regressions in core invariants (markdown source of truth, governance cascade, focus/dropped, alias uniqueness, delete cascades, reindex roundtrips).

### Scope
- Pure modules: refs, templates, config.
- Heavy coverage on Storage: CRUD, subtopics+sources, aliases+resolve, links, governance attach, task pack assembly (focus narrowing + dropped, cascade order, always_include), uses graph + suggest, reindex, delete cascades, maintenance.
- Used isolated tmp_path homes per test via Storage(root=...) + context manager.
- Added `[tool.pytest.ini_options]` to pyproject.toml.

### Behavior changes discovered and corrected while testing
While writing delete-cascade tests, noticed that deleting a parent Component nulled the DB `component_parent` but left the child's `_meta.md` (and thus `get_entity` / `get_repo_component`) still pointing at the now-deleted parent. Same for governance links removed from table but not rewritten into owner entity markdown.

**Fix:** during `delete_entity` for COMPONENT and GOVERNANCE, capture affected children/owners and rewrite their markdown via `_write_meta` / `_sync_governance_meta` so the filesystem (source of truth) stays consistent. DB was already updated. This upholds the "Markdown files are authoritative" rule.

### Non-goals / deferred
- Full tool-layer tests via FastMCP (storage is the authoritative implementation).
- Property-based / large scale FTS scoring tests (can be added with real usage data).
- No change to public contract.

Tests: `uv run pytest`. All pass.

