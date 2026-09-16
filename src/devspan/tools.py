from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import ComponentKind, EntityRef, EntityType, ExternalRef
from .refs import parse_ref, slugify
from .storage import Storage


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def register(mcp: Any, storage: Storage) -> None:
    """Attach all DevSpan tools to the given FastMCP instance."""

    # ---------- entity creation ----------

    @mcp.tool
    def create_component(
        slug: str,
        description: str = "",
        kind: str = "system",
        aliases: list[str] | None = None,
        uses: list[str] | None = None,
        governance: list[str] | None = None,
    ) -> dict:
        """Create a new Component entity.

        A Component is any coherent unit of functionality that you hold context
        about: an internal subsystem, an external service, an API, a database,
        a library, or a tool. The `kind` tag lets you filter later.

        Args:
            slug: lowercase a-z0-9- identifier (e.g. "api-gateway").
            description: one-paragraph prose description.
            kind: one of "system" | "service" | "api" | "database" | "library" | "tool".
                Default "system" (generic fallback).
            aliases: optional short nicknames (e.g. ["gw", "the gateway"]).
                Must be globally unique across all entities.
            uses: optional list of component slugs this component depends on.
                Used by suggest_task_links for graph traversal.
            governance: optional list of governance refs that apply to this
                component (e.g. ["governance:security-policy"]).

        Creates a directory with scaffolded subtopics (overview, auth,
        integration, gotchas) that you can fill in or delete.
        """
        s = slugify(slug)
        storage.create_entity(
            EntityType.COMPONENT,
            s,
            name=slug,
            description=description,
            kind=ComponentKind(kind),
            aliases=aliases or [],
            uses=uses or [],
            governance=governance or [],
        )
        return {"ref": f"component:{s}", "created": True}

    @mcp.tool
    def create_repo(
        slug: str,
        description: str = "",
        component: str | None = None,
        aliases: list[str] | None = None,
        governance: list[str] | None = None,
    ) -> dict:
        """Create a new Repo entity.

        Repos hold long-lived facts about a codebase: style, testing, layout,
        local-dev setup, conventions. A repo optionally belongs to a parent
        Component (e.g. gateway-proxy-repo -> component:api-gateway).

        Args:
            slug: lowercase a-z0-9- identifier (e.g. "ui-repo").
            description: one-paragraph prose description.
            component: optional parent component slug.
            aliases: optional short nicknames. Globally unique.
            governance: optional governance refs that apply.

        Creates scaffolded subtopics (overview, style, testing, local-dev).
        """
        s = slugify(slug)
        storage.create_entity(
            EntityType.REPO,
            s,
            name=slug,
            description=description,
            component_parent=component,
            aliases=aliases or [],
            governance=governance or [],
        )
        return {"ref": f"repo:{s}", "created": True}

    @mcp.tool
    def create_task(
        slug: str,
        description: str = "",
        aliases: list[str] | None = None,
        governance: list[str] | None = None,
    ) -> dict:
        """Create a new Task entity.

        Tasks are transient units of work (a feature, a bug, an investigation)
        that compose context by linking specific Component/Repo/Governance refs
        via link_task. Scaffolded subtopics: goal, plan, notes.

        Args:
            slug: lowercase a-z0-9- identifier (e.g. "fix-login-redirect").
            description: one-paragraph prose description.
            aliases: optional short nicknames.
            governance: optional governance refs that apply directly to this task.
        """
        s = slugify(slug)
        storage.create_entity(
            EntityType.TASK,
            s,
            name=slug,
            description=description,
            aliases=aliases or [],
            governance=governance or [],
        )
        return {"ref": f"task:{s}", "created": True}

    @mcp.tool
    def create_governance(
        slug: str,
        description: str = "",
        aliases: list[str] | None = None,
    ) -> dict:
        """Create a new Governance entity — a reusable guideline.

        Governance entities hold cross-cutting rules that apply to multiple
        components/repos/tasks: security policies, API design standards,
        branding guidelines, user preferences. Any other entity can reference
        them via `governance: [...]` in its frontmatter or via add_governance.

        When assembling a task pack, governance refs cascade: the task's own
        governance + governance attached to each linked component/repo + parent
        components of linked repos. All deduped.

        Scaffolded subtopics: overview, rules.
        """
        s = slugify(slug)
        storage.create_entity(
            EntityType.GOVERNANCE,
            s,
            name=slug,
            description=description,
            aliases=aliases or [],
        )
        return {"ref": f"governance:{s}", "created": True}

    # ---------- listings ----------

    @mcp.tool
    def list_components(kind: str | None = None) -> list[dict]:
        """List all Components, optionally filtered by kind.

        Args:
            kind: optional filter — "system" | "service" | "api" | "database"
                | "library" | "tool".
        """
        k = ComponentKind(kind) if kind else None
        return storage.list_entities(EntityType.COMPONENT, kind=k)

    @mcp.tool
    def list_repos() -> list[dict]:
        """List all Repos."""
        return storage.list_entities(EntityType.REPO)

    @mcp.tool
    def list_tasks() -> list[dict]:
        """List all Tasks."""
        return storage.list_entities(EntityType.TASK)

    @mcp.tool
    def list_governance_entities() -> list[dict]:
        """List all Governance entities."""
        return storage.list_entities(EntityType.GOVERNANCE)

    @mcp.tool
    def delete_entity(ref: str) -> dict:
        """Delete an entity and ALL its subtopics. Destructive.

        Also cleans up: aliases, task_links referencing this entity, governance
        links, uses-graph edges, and nullifies repo->component parent pointers.

        Requires an entity-level ref (no subtopic).
        """
        parsed = parse_ref(ref)
        if parsed.subtopic:
            raise ValueError("delete_entity requires an entity ref, not a subtopic")
        storage.delete_entity(parsed.type, parsed.slug)
        return {"ref": ref, "deleted": True}

    # ---------- aliases + resolution ----------

    @mcp.tool
    def add_alias(ref: str, alias: str) -> dict:
        """Add a short nickname for an entity. Globally unique.

        Example: add_alias("component:api-gateway", "gw") — then resolve_ref("gw")
        returns the component.
        """
        parsed = parse_ref(ref)
        if parsed.subtopic:
            raise ValueError("aliases attach to entities, not subtopics")
        aliases = storage.add_alias(parsed.type, parsed.slug, alias.lower())
        return {"ref": ref, "aliases": aliases}

    @mcp.tool
    def remove_alias(ref: str, alias: str) -> dict:
        """Remove an alias from an entity."""
        parsed = parse_ref(ref)
        if parsed.subtopic:
            raise ValueError("aliases attach to entities, not subtopics")
        aliases = storage.remove_alias(parsed.type, parsed.slug, alias.lower())
        return {"ref": ref, "aliases": aliases}

    @mcp.tool
    def resolve_ref(query: str, type_filter: str | None = None) -> list[dict]:
        """Resolve a fuzzy query ("the gateway", "gw", "auth-gw") to candidate refs.

        Checks exact slug, exact alias, and case-insensitive name substring.
        Returns ranked candidates [{ref, source, score}] — call this before
        writing if the user refers to something by nickname or description.

        Args:
            query: free text.
            type_filter: optional — restrict to "component"|"repo"|"task"|"governance".
        """
        t = EntityType(type_filter) if type_filter else None
        return storage.resolve_ref(query, type_filter=t)

    # ---------- context CRUD ----------

    @mcp.tool
    def get_context(ref: str) -> dict:
        """Read the current context for an entity or a single subtopic.

        Accepts an entity ref ("component:api-gateway") or a subtopic ref
        ("component:api-gateway/auth"). For entity refs, returns the meta +
        all subtopics.
        """
        parsed = parse_ref(ref)
        if parsed.subtopic:
            sub = storage.get_subtopic(parsed)
            if sub is None:
                raise KeyError(f"{ref} not found")
            return {
                "ref": ref,
                "subtopic": sub.slug,
                "content": sub.content,
                "updated_at": sub.updated_at,
                "source_url": sub.source_url,
                "source_name": sub.source_name,
                "source_fetched_at": sub.source_fetched_at,
            }
        entity = storage.get_entity(parsed.type, parsed.slug)
        return {
            "ref": ref,
            "type": entity.type.value,
            "name": entity.meta.name,
            "description": entity.meta.description,
            "kind": entity.meta.kind.value if entity.meta.kind else None,
            "component": entity.meta.component,
            "aliases": entity.meta.aliases,
            "uses": entity.meta.uses,
            "governance": entity.meta.governance,
            "links": entity.meta.links,
            "external_refs": [e.model_dump() for e in entity.meta.external_refs],
            "created_at": entity.meta.created_at,
            "updated_at": entity.meta.updated_at,
            "subtopics": [
                {
                    "slug": s.slug,
                    "content": s.content,
                    "updated_at": s.updated_at,
                    "source_url": s.source_url,
                    "source_name": s.source_name,
                    "source_fetched_at": s.source_fetched_at,
                }
                for s in entity.subtopics
            ],
        }

    @mcp.tool
    def upsert_context(ref: str, content: str) -> dict:
        """Create or overwrite a subtopic's full content.

        Requires a subtopic ref. Parent entity must already exist.
        Clears any previously stored source_url/source_name when content is
        overwritten without source metadata.
        """
        parsed = parse_ref(ref)
        sub = storage.upsert_subtopic(parsed, content)
        return {"ref": ref, "updated_at": sub.updated_at, "upserted": True}

    @mcp.tool
    def append_context(ref: str, content: str) -> dict:
        """Append content to a subtopic, creating it if missing.

        Separates appended content from existing with a blank line.
        """
        parsed = parse_ref(ref)
        sub = storage.append_subtopic(parsed, content)
        return {"ref": ref, "updated_at": sub.updated_at, "appended": True}

    @mcp.tool
    def delete_context(ref: str) -> dict:
        """Delete a single subtopic. Parent entity is preserved."""
        parsed = parse_ref(ref)
        if not parsed.subtopic:
            raise ValueError("delete_context requires a subtopic ref")
        existed = storage.delete_subtopic(parsed)
        return {"ref": ref, "deleted": existed}

    # ---------- imported content + sources ----------

    @mcp.tool
    def import_content(
        ref: str,
        content: str,
        source_url: str,
        source_name: str = "",
    ) -> dict:
        """Store content fetched from an external source as a subtopic.

        Use this after another MCP tool (e.g. an Atlassian MCP for Confluence)
        returns page content — DevSpan then owns it as a snapshot with
        source tracking. `source_fetched_at` is set to now automatically.

        Args:
            ref: subtopic ref to write into, e.g. "component:api-gateway/confluence-auth-doc".
            content: the fetched text/markdown.
            source_url: the canonical source URL.
            source_name: short label ("confluence", "notion", "github-wiki").

        Later call refresh_source(ref) to get the URL back and re-fetch.
        """
        parsed = parse_ref(ref)
        if not parsed.subtopic:
            raise ValueError("import_content requires a subtopic ref")
        sub = storage.upsert_subtopic(
            parsed,
            content,
            source_url=source_url,
            source_name=source_name,
            source_fetched_at=_now(),
        )
        return {
            "ref": ref,
            "updated_at": sub.updated_at,
            "source_url": sub.source_url,
            "source_name": sub.source_name,
            "source_fetched_at": sub.source_fetched_at,
        }

    @mcp.tool
    def refresh_source(ref: str) -> dict:
        """Return the source_url for a subtopic so the caller can re-fetch.

        DevSpan does NOT fetch. The caller (LLM) uses another MCP tool or
        HTTP fetcher to retrieve fresh content, then calls import_content again
        with the same ref.
        """
        parsed = parse_ref(ref)
        sub = storage.get_subtopic(parsed)
        if sub is None:
            raise KeyError(f"{ref} not found")
        if not sub.source_url:
            raise ValueError(f"{ref} has no source_url — nothing to refresh")
        return {
            "ref": ref,
            "source_url": sub.source_url,
            "source_name": sub.source_name,
            "source_fetched_at": sub.source_fetched_at,
        }

    @mcp.tool
    def list_stale_sources(older_than_iso: str) -> list[dict]:
        """List imported subtopics whose source_fetched_at is older than a cutoff.

        Args:
            older_than_iso: ISO-8601 UTC timestamp cutoff, e.g. "2026-04-12T00:00:00+00:00".
                Subtopics with source_fetched_at strictly less than this are returned.
        """
        return storage.list_stale_sources(older_than_iso)

    # ---------- task composition ----------

    @mcp.tool
    def link_task(task_slug: str, refs: list[str]) -> dict:
        """Wire refs (component/repo/governance, optionally with subtopic) into a task.

        Subtopic-level refs keep packs focused. Governance refs attached here
        also cascade to the assembled pack; governance attached to linked
        components/repos cascades automatically too.
        """
        return {"task": f"task:{task_slug}", "links": storage.link_task(task_slug, refs)}

    @mcp.tool
    def unlink_task(task_slug: str, refs: list[str]) -> dict:
        """Remove refs from a task's link list. Idempotent."""
        return {"task": f"task:{task_slug}", "links": storage.unlink_task(task_slug, refs)}

    @mcp.tool
    def get_task_pack(
        task_slug: str,
        include_always: bool = True,
        focus: bool = True,
        per_entity_top_k: int = 3,
        min_score: float | None = None,
    ) -> dict:
        """Assemble the full context pack for a task.

        Returns the task's own meta+subtopics, all resolved linked refs, and a
        deduplicated governance section. If include_always is True (default),
        refs from config.json `always_include` are merged in.

        When focus is True (default), entity-level refs with more than
        per_entity_top_k subtopics are FTS-narrowed against the task's
        description + own notes — only the top-K most relevant subtopics are
        included; the rest are returned in `dropped` for on-demand pull via
        get_subtopic / get_context. Subtopic-level refs (component:foo/bar)
        bypass narrowing.

        Args:
            task_slug: the task to assemble.
            include_always: merge config.always_include refs (default True).
            focus: enable FTS-narrowing of entity-level refs (default True).
            per_entity_top_k: max subtopics to include per narrowed entity (default 3).
            min_score: optional bm25 relevance floor (negated bm25; higher = more
                relevant; default None means top-K with no hard cutoff).
        """
        pack = storage.get_task_pack(
            task_slug,
            include_always=include_always,
            focus=focus,
            per_entity_top_k=per_entity_top_k,
            min_score=min_score,
        )
        return {
            "task": {
                "ref": f"task:{pack.task.slug}",
                "name": pack.task.meta.name,
                "description": pack.task.meta.description,
                "subtopics": [
                    {"slug": s.slug, "content": s.content} for s in pack.task.subtopics
                ],
                "external_refs": [e.model_dump() for e in pack.task.meta.external_refs],
            },
            "linked": [{"ref": r, "content": c} for r, c in pack.linked],
            "governance": [{"ref": r, "content": c} for r, c in pack.governance],
            "dropped": pack.dropped,
        }

    @mcp.tool
    def suggest_task_links(
        task_slug: str,
        anchors: list[str] | None = None,
        depth: int = 3,
        top_k: int = 10,
    ) -> list[dict]:
        """Propose candidate refs to link into a task.

        Walks the `uses` graph from the anchors (or existing links if anchors
        is None), collects components within `depth` hops, FTS-scores each
        candidate's subtopics against the task's description + notes, and
        returns top-K suggestions that aren't already linked.

        Args:
            task_slug: the task to suggest for.
            anchors: optional list of refs to traverse from. If omitted, uses
                the task's existing links.
            depth: graph traversal depth, default 3 (configurable).
            top_k: max number of suggestions, default 10.
        """
        return storage.suggest_task_links(
            task_slug, anchors=anchors, depth=depth, top_k=top_k
        )

    # ---------- governance ----------

    @mcp.tool
    def add_governance(ref: str, governance_ref: str) -> dict:
        """Attach a governance ref to a component/repo/task.

        The governance content will be included in any task pack that touches
        this entity (directly via link_task, or via parent-component cascade
        for repos). Cannot attach governance to another governance entity.
        """
        parsed = parse_ref(ref)
        return {
            "ref": ref,
            "governance": storage.add_governance(parsed, governance_ref),
        }

    @mcp.tool
    def remove_governance(ref: str, governance_ref: str) -> dict:
        """Detach a governance ref from an entity."""
        parsed = parse_ref(ref)
        return {
            "ref": ref,
            "governance": storage.remove_governance(parsed, governance_ref),
        }

    # ---------- task external refs ----------

    @mcp.tool
    def add_external_ref(
        task_slug: str,
        system: str,
        id: str,
        url: str = "",
    ) -> list[dict]:
        """Attach a reference to an external tracking system (Jira, GitHub, etc.).

        DevSpan does not fetch these — it just stores pointers. Use a
        separate MCP server (Atlassian, GitHub, etc.) to retrieve current state.

        Args:
            task_slug: the task.
            system: short label ("jira", "github", "linear").
            id: the external identifier ("BUG-1234", "pr/456").
            url: optional canonical URL.
        """
        refs = storage.add_external_ref(
            task_slug, ExternalRef(system=system, id=id, url=url)
        )
        return [r.model_dump() for r in refs]

    @mcp.tool
    def remove_external_ref(task_slug: str, system: str, id: str) -> list[dict]:
        """Detach an external reference from a task."""
        refs = storage.remove_external_ref(task_slug, system, id)
        return [r.model_dump() for r in refs]

    # ---------- search ----------

    @mcp.tool
    def search(query: str, entity_type: str | None = None, limit: int = 20) -> list[dict]:
        """Full-text search (SQLite FTS5) across all subtopic content.

        Args:
            query: free text; treated as a phrase (operators not supported).
            entity_type: optional filter — "component"|"repo"|"task"|"governance".
            limit: max results, default 20.
        """
        et = EntityType(entity_type) if entity_type else None
        return storage.search(query, entity_type=et, limit=limit)

    # ---------- config: always_include ----------

    @mcp.tool
    def get_config() -> dict:
        """Return the current DevSpan config (always_include, workspaces)."""
        return storage.config.as_dict()

    @mcp.tool
    def add_always_include(ref: str) -> list[str]:
        """Add a ref to the always_include list.

        Any ref in this list is automatically included in every task pack.
        Typical use: a personal-prefs governance entity you want everywhere.
        """
        parse_ref(ref)  # validate
        return storage.config.add_always_include(ref)

    @mcp.tool
    def remove_always_include(ref: str) -> list[str]:
        """Remove a ref from the always_include list."""
        return storage.config.remove_always_include(ref)

    # ---------- workspace / Roots ----------

    @mcp.tool
    def bind_workspace(path: str, repo_slug: str) -> dict:
        """Associate a local workspace path with a repo slug.

        Once bound, get_current_workspace(path) returns the repo slug so the
        LLM can auto-select relevant context when you're working in that dir.

        The MCP client's Roots capability is the canonical source of the
        current workspace path; this tool expects that path passed in.
        """
        parse_ref(f"repo:{repo_slug}")  # validate repo slug form
        if not storage.entity_exists(EntityType.REPO, repo_slug):
            raise KeyError(f"repo:{repo_slug} not found — create it first")
        ws = storage.config.bind_workspace(path, repo_slug)
        return {"path": str(Path(path).resolve()), "repo": repo_slug, "workspaces": ws}

    @mcp.tool
    def unbind_workspace(path: str) -> dict:
        """Remove a workspace→repo binding."""
        ws = storage.config.unbind_workspace(path)
        return {"workspaces": ws}

    @mcp.tool
    def get_current_workspace(path: str) -> dict:
        """Resolve a workspace path to its bound repo (and parent component, if any).

        Args:
            path: absolute path to check. The MCP client supplies this from its
                Roots; DevSpan does not read Roots directly in v0.
        """
        repo_slug = storage.config.lookup_workspace(path)
        if not repo_slug:
            return {"path": str(Path(path).resolve()), "repo": None, "component": None}
        component = storage.get_repo_component(repo_slug)
        return {
            "path": str(Path(path).resolve()),
            "repo": f"repo:{repo_slug}",
            "component": f"component:{component}" if component else None,
        }

    # ---------- maintenance ----------

    @mcp.tool
    def reindex() -> dict:
        """Rebuild the SQLite + FTS5 index from markdown files on disk.

        Use after manual edits on disk, or if the index seems stale.
        Filesystem is the source of truth.
        """
        return storage.reindex()

    @mcp.tool
    def tail_logs(n: int = 50) -> list[str]:
        """Return the most recent lines from the persistent usage/debug log.

        The log at ~/.devspan/logs/devspan.log (rotating) captures
        tool invocations, pack assemblies (with dropped counts, sizes, timings),
        entity creates, links, governance attachments, resolves, suggestions,
        context writes, and workspace binds. This is the primary signal for
        understanding real usage and tuning focus/governance behavior.

        Args:
            n: number of lines to return (default 50).
        """
        return storage.tail_logs(n)
