# Usage / Trial Logs (Development Only)

This directory is for capturing ContextForge usage logs **inside the source repo** during development and dogfooding.

## Why this exists

The normal logs live at `~/.contextforge/logs/contextforge.log` (or `$CONTEXTFORGE_HOME`).
Those do not travel with the git checkout.

For evaluating the system it is useful to have the raw event stream live inside this repo so it can be:

- Inspected after working "at home" or on another machine
- Committed (selectively) as evidence
- Diffed over time
- Analyzed without needing access to the original user's home directory

## How to enable repo-local logging

Set one of these environment variables when starting the ContextForge MCP server:

```bash
# Preferred for dev (simpler)
export CONTEXTFORGE_DEV_LOG_DIR="$(pwd)/.system/usage-logs"

# Or the explicit file form
# export CONTEXTFORGE_LOG_FILE="$(pwd)/.system/usage-logs/contextforge.log"

# Optional: more detail
export CONTEXTFORGE_LOG_LEVEL=INFO
```

Then run normally:

```bash
uv run contextforge
```

Or put it in your project-scoped Cursor config (`.cursor/mcp.json` for this repo):

```json
{
  "mcpServers": {
    "contextforge": {
      "command": "uv",
      "args": ["run", "--directory", "/ABSOLUTE/PATH/TO/context-forge", "contextforge"],
      "env": {
        "CONTEXTFORGE_LOG_LEVEL": "INFO",
        "CONTEXTFORGE_DEV_LOG_DIR": "/ABSOLUTE/PATH/TO/context-forge/.system/usage-logs"
      }
    }
  }
}
```

## Behavior

- When `CONTEXTFORGE_LOG_FILE` is set, the **same events** are written to both the normal home log **and** the path you specified.
- This gives you "both places for a while".
- The file uses the same rotating text format as the home log (easy to `tail`, `grep`, or parse).
- You can point it at any path — it does not have to be under `.system/`.

## What gets logged

See the structured `pack:*`, `entity:*`, `task:linked`, `governance:*`, `ref:resolved`, `suggest:*`, `context:*`, etc. messages. These are the primary signals for judging whether focus narrowing, governance, suggest_task_links, etc. are earning their keep.

## Git and sharing

The `*.log` files are gitignored by default (see root `.gitignore` addition) so you don't accidentally commit large or private logs.

When you have useful data from a trial period, you can:

- `git add -f .system/usage-logs/some-specific-run.log`
- Or copy the file out for analysis at home.

## Cleanup

Feel free to delete old log files in this directory. They are purely development artifacts for this project.

---

This setup was added so trial runs can travel with the checkout.
