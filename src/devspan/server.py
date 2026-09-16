from __future__ import annotations

import atexit
import logging
import os
import sys

from fastmcp import FastMCP

from . import resources as _resources
from . import tools as _tools
from .storage import Storage


def _setup_logging() -> None:
    """Configure stderr logging for the MCP server (stdout is reserved for protocol).

    Persistent file logging (rotating text):
    - Always: <DEVSPAN_HOME>/logs/devspan.log (via Storage)
    - Optional extra: via DEVSPAN_LOG_FILE or DEVSPAN_DEV_LOG_DIR
      (see setup_extra_logging in storage.py).

    The extra mechanism lets you write the same events to a second location
    (e.g. inside this repo under .system/usage-logs/) so logs travel with the
    checkout for evaluation. You get *both* locations when the var is set.

    Control verbosity with DEVSPAN_LOG_LEVEL=DEBUG (affects stderr + all files).
    """
    level_name = os.environ.get("DEVSPAN_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    )
    logging.getLogger("devspan").setLevel(level)
    logging.getLogger("devspan").addHandler(handler)

    # Support repo-local / extra dev logs early (before Storage is created).
    # This is how you make usage data travel with the source repo.
    from .storage import setup_extra_logging
    setup_extra_logging()

INSTRUCTIONS = """\
DevSpan: local context management for cross-repo engineering work.

Entity types:
- Component: a coherent unit of functionality (system/service/api/database/library/tool).
  Kinds: system | service | api | database | library | tool. Can declare a `uses`
  dependency graph over other components. Repos can belong to a parent component.
- Repo: a codebase — style, testing, layout, conventions. Optionally has a parent Component.
- Task: a transient unit of work. Links specific Component/Repo/Governance refs to
  compose its context pack. Can carry external_refs (Jira, GitHub, etc.).
- Governance: reusable cross-cutting guidelines (security policy, API standards,
  user prefs, branding). Any other entity can reference them. They cascade into
  task packs from the task + linked components + linked repos + parent components.

Ref grammar:
  type:slug              # whole entity
  type:slug/subtopic     # one document within an entity

Types: component | repo | task | governance. Slugs/subtopics: lowercase a-z0-9-.

Data lives under ~/.devspan/ (override with DEVSPAN_HOME). Markdown files
on disk are the source of truth; SQLite+FTS5 is a derived index. The `reindex` tool
rebuilds it from disk.

Config at ~/.devspan/config.json holds `always_include` refs (auto-merged into
every task pack) and workspace->repo bindings.

Logs (for usage analysis): ~/.devspan/logs/devspan.log (rotating text file).
Key events include pack assembly (with dropped/focus details), creates, links,
governance cascade attachments, resolves, suggestions, and writes. Use `tail_logs`
tool or external tail to inspect. Set DEVSPAN_LOG_LEVEL=DEBUG for FTS scores.

Additional dev location: set DEVSPAN_DEV_LOG_DIR (a directory) or
DEVSPAN_LOG_FILE (exact file) to write the same events to a second rotating file.
This is how repo-local logs are produced so they travel with the checkout.

Key flows:
- Use resolve_ref when the user mentions a name/nickname ("the gateway") rather
  than a slug — it returns ranked candidates.
- Use suggest_task_links to propose refs based on a task's description + the
  `uses` graph (default depth 3).
- Use import_content + refresh_source for content fetched from external MCPs
  (Atlassian/Confluence, GitHub, etc.) — DevSpan stores the snapshot and
  tracks source_url/source_fetched_at. Refreshing is the caller's job.
"""

_setup_logging()
mcp = FastMCP("DevSpan", instructions=INSTRUCTIONS)
_storage = Storage()
_tools.register(mcp, _storage)
_resources.register(mcp, _storage)


def _shutdown() -> None:
    """Best-effort cleanup of the main thread's SQLite connection."""
    _storage.close()


atexit.register(_shutdown)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
