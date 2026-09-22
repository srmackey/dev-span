# DevSpan

DevSpan gives an AI client durable engineering context across repositories: components, repos, tasks, and governance, stored as markdown and composed per task.

Not a wiki, not standing guidance, and not a bulletin. It does not fetch external pages. An external ref is a pointer. A snapshot is stored only when the caller hands over the text.

Built for the cross-repo reality: a single task touches the UI repo, the API repo, the gateway, a service you do not own, and a database. Capture the reusable facts once and compose them for the task.

**Lineage:** evolved from the earlier file-based Cursor framework [ai-context-framework](https://github.com/srmackey/ai-context-framework) (rules · packs · graph · slash commands). That repo is archived as the v1 path; this project is the active implementation.

Structure: [DESIGN.md](DESIGN.md). What moved: [CHANGELOG.md](CHANGELOG.md).

## Model

- **Component** — a coherent unit of functionality. Kinds: `system | service | api | database | library | tool`. Can declare a `uses` dependency graph over other components.
- **Repo** — a codebase. Optionally belongs to a parent Component (e.g. `gateway-proxy-repo → component:api-gateway`).
- **Task** — a transient unit of work that composes context by linking specific Component/Repo/Governance refs. Can carry `external_refs` to Jira/GitLab/Confluence/etc.
- **Governance** — reusable cross-cutting guidelines (security policy, API design standards, user prefs, branding). Any other entity can reference them; they cascade into task packs automatically.

**Ref grammar:** `type:slug` (entity) or `type:slug/subtopic` (one document within an entity).

Examples: `component:api-gateway`, `component:api-gateway/auth`, `repo:ui-repo/testing`, `task:fix-login-redirect`, `governance:security-policy/data-handling`.

## Storage

All data lives under `~/.devspan/` (override with `DEVSPAN_HOME`):

```
~/.devspan/
  components/{slug}/_meta.md, {subtopic}.md
  repos/{slug}/_meta.md, {subtopic}.md
  tasks/{slug}/_meta.md, {subtopic}.md
  governance/{slug}/_meta.md, {subtopic}.md
  .index/devspan.db       # SQLite + FTS5, rebuildable via `reindex`
  config.json                  # always_include refs + workspace bindings
  logs/devspan.log        # persistent usage + debug (rotating)
```

Markdown files are the source of truth. The SQLite index is derived — if it drifts, call `reindex`.

`Storage` opens **one SQLite connection per thread** (`threading.local()`) with `PRAGMA journal_mode=WAL` so FastMCP's worker threads can each call in safely. This is load-bearing — don't cache a `Connection` on the instance or remove the WAL pragma.

New entities get scaffolded subtopics:
- Components: `overview.md`, `auth.md`, `integration.md`, `gotchas.md`
- Repos: `overview.md`, `style.md`, `testing.md`, `local-dev.md`
- Tasks: `goal.md`, `plan.md`, `notes.md`
- Governance: `overview.md`, `rules.md`

Delete the ones you don't want.

## Install & run

[`uv`](https://docs.astral.sh/uv/) is the expected package manager (install via `brew install uv` or Astral's installer).

```bash
cd /path/to/dev-span
uv sync
uv run devspan            # stdio MCP server
```

Tests (pytest is a dev dependency):

```bash
uv sync
uv run pytest
```

> Behind an SSL-inspecting proxy? If `uv sync` fails with `invalid peer certificate: UnknownIssuer`, add `--system-certs` to the `uv` commands (or `export UV_SYSTEM_CERTS=1`).

Logs go to stderr **and** to `~/.devspan/logs/devspan.log` (rotating text file, on by default). The file is the durable record for usage analysis and trials.

Default level is `INFO` (pack assembly summaries, creates, links, governance, resolves, etc.). Set `DEVSPAN_LOG_LEVEL=DEBUG` for full FTS scoring breakdowns per entity — useful for tuning `per_entity_top_k` and `min_score`.

Use the `tail_logs(n)` tool to inspect recent activity from inside the MCP.

For development / dogfooding where you want the same events written to a second location (e.g. inside the source repo so logs travel with the checkout), set:
- `DEVSPAN_DEV_LOG_DIR=/path/to/desired/dir`   (recommended), or
- `DEVSPAN_LOG_FILE=/path/to/specific.log`

You get both the normal home log *and* the extra location.

## Wire into Cursor

**Install it globally, not per-project.** DevSpan is a single global store
(`~/.devspan/`) meant to serve *every* repo you work in. The `--directory`
below only tells `uv` where this server's *code* lives — the running server reads
`~/.devspan/` regardless of which workspace is open, so **you never need to add
the dev-span folder to your other repos.** Wire it once, globally, and it's
available everywhere.

### 1. Register the MCP server globally

Add it to your global Cursor MCP config (`~/.cursor/mcp.json`, or your
`mcp-manager` proxy config if you use one), replacing the placeholder with this
repo's path on your machine:

```json
{
  "mcpServers": {
    "devspan": {
      "command": "uv",
      "args": ["run", "--directory", "/ABSOLUTE/PATH/TO/dev-span", "devspan"]
    }
  }
}
```

Behind an SSL-inspecting proxy, add `"--system-certs"` as the first entry in `args`,
or set `UV_SYSTEM_CERTS=1` on the server's `env`. Restart Cursor (or toggle the
server under **Settings → MCP**) and confirm the `devspan` tools appear.

> A project-scoped [.cursor/mcp.json](.cursor/mcp.json) is also committed in this
> repo, but it only activates when *this* repo is the open workspace — fine for
> hacking on DevSpan itself, not for using it across your work.

### 2. Make the router rule global too

The MCP registration gives the agent the *tools*; the
[.cursor/rules/devspan-router.mdc](.cursor/rules/devspan-router.mdc) rule
gives it the *behavior* (when to recall and capture context proactively). A rule
that lives only in this repo won't apply in your other repos — so it must be global
as well. Two equivalent options:

- **Symlink** the rule into your global Cursor rules location (single source of
  truth — edits here propagate automatically). On Windows this needs Developer Mode
  or an elevated `mklink`.
- **Copy** the rule into your global Cursor rules location (more portable; re-copy
  after edits).

Either way the rule is `alwaysApply: true`, so once it's global it's in context for
every session — that's what lets the agent use DevSpan without being told to.

## Tools

The tools, what they take, and what they change are in [docs/tools.md](docs/tools.md). Each tool sets `readOnlyHint`, `destructiveHint`, `idempotentHint`, and `openWorldHint`. None of them are open to the network.

On initialize the server returns the operating note from the server code. This page does not repeat it.

## Trust boundary

- Transport is stdio. The host starts a local process as the user who launched it.
- It reads and writes markdown under `DEVSPAN_HOME` (default `~/.devspan`), plus a derived SQLite index in that same folder.
- It does not fetch URLs. `import_content` stores text the caller already has. `refresh_source` returns the stored URL so the caller can fetch it elsewhere.
- It does not take a credential.
- `delete_entity` removes an entity, its documents, and the links that pointed at it.

How to report a vulnerability is in [SECURITY.md](SECURITY.md).

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- FastMCP 2, over stdio

There is no published package. Clone the repository and run it from the checkout, as in Install and run above.

## Resources

- `context://component/{slug}` / `context://repo/{slug}` / `context://task/{slug}` / `context://governance/{slug}` — full entity as markdown
- `context://{type}/{slug}/{subtopic}` — single subtopic
- `pack://task/{slug}` — assembled task pack (separate scheme avoids colliding with `task/{slug}/{subtopic}`)

## Smoke test

After wiring it into Cursor, ask the agent to run these (or call them from the MCP panel):

1. `create_component(slug="api-gateway", kind="system", description="Our edge proxy")`
2. `upsert_context(ref="component:api-gateway/auth", content="OAuth2 with PKCE; tokens rotate hourly.")`
3. `create_governance(slug="security-policy", description="Company-wide security baseline")`
4. `add_governance(ref="component:api-gateway", governance_ref="governance:security-policy")`
5. `create_task(slug="demo-task", description="Kicking the tires")`
6. `link_task(task_slug="demo-task", refs=["component:api-gateway/auth"])`
7. `get_task_pack(task_slug="demo-task")` — you should see the auth subtopic AND the security-policy content (cascaded through the governance link on the component).

## License

MIT. Runtime deps are permissive (MIT/BSD/Apache-2.0) — no copyleft.
