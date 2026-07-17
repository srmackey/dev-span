from __future__ import annotations

from typing import Any

from .models import Entity, EntityRef, EntityType, TaskPack
from .storage import Storage


def _render_entity_markdown(entity: Entity) -> str:
    out = [f"# {entity.meta.name} ({entity.type.value}"]
    if entity.meta.kind:
        out[-1] += f": {entity.meta.kind.value}"
    out[-1] += ")"
    out.append("")
    if entity.meta.aliases:
        out.append(f"**Aliases:** {', '.join(entity.meta.aliases)}")
    if entity.meta.component:
        out.append(f"**Component:** {entity.meta.component}")
    if entity.meta.uses:
        out.append(f"**Uses:** {', '.join(entity.meta.uses)}")
    if entity.meta.governance:
        out.append(f"**Governance:** {', '.join(entity.meta.governance)}")
    if entity.meta.links:
        out.append("**Links:**")
        out.extend(f"- {ref}" for ref in entity.meta.links)
    if entity.meta.external_refs:
        out.append("**External refs:**")
        for e in entity.meta.external_refs:
            label = f"{e.system}:{e.id}"
            if e.url:
                label += f" ({e.url})"
            out.append(f"- {label}")
    if out[-1] != "":
        out.append("")
    if entity.meta.description:
        out.extend([entity.meta.description.strip(), ""])
    for sub in entity.subtopics:
        out.append(f"## {sub.slug}")
        if sub.source_url:
            out.append(f"_Source: {sub.source_name or 'external'} — {sub.source_url}"
                       f" (fetched {sub.source_fetched_at})_")
            out.append("")
        out.append(sub.content.rstrip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def _render_pack_markdown(pack: TaskPack) -> str:
    out = [f"# Task Pack: {pack.task.meta.name}", ""]
    if pack.task.meta.description:
        out.extend([pack.task.meta.description.strip(), ""])
    if pack.task.meta.external_refs:
        out.append("**External refs:**")
        for e in pack.task.meta.external_refs:
            label = f"{e.system}:{e.id}"
            if e.url:
                label += f" ({e.url})"
            out.append(f"- {label}")
        out.append("")
    out.append("## Task Notes")
    if pack.task.subtopics:
        for sub in pack.task.subtopics:
            out.append(f"### {sub.slug}")
            out.append(sub.content.rstrip())
            out.append("")
    else:
        out.extend(["_(no task-specific notes yet)_", ""])
    if pack.governance:
        out.append("## Governance")
        for ref_str, content in pack.governance:
            out.append(f"### {ref_str}")
            out.append(content.rstrip())
            out.append("")
    out.append("## Linked Context")
    if not pack.linked:
        out.append("_(no linked refs — use link_task to wire in components/repos)_")
    for ref_str, content in pack.linked:
        out.append(f"### {ref_str}")
        out.append(content.rstrip())
        out.append("")
    if pack.dropped:
        out.append("## Dropped (filtered out by focus)")
        out.append("_Pull these via get_subtopic / get_context if needed._")
        out.append("")
        out.extend(f"- {ref}" for ref in pack.dropped)
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def register(mcp: Any, storage: Storage) -> None:
    """Attach ContextForge resources to the given FastMCP instance."""

    # Full entity views
    @mcp.resource("context://component/{slug}")
    def component_resource(slug: str) -> str:
        """Full Component entity rendered as markdown."""
        return _render_entity_markdown(storage.get_entity(EntityType.COMPONENT, slug))

    @mcp.resource("context://repo/{slug}")
    def repo_resource(slug: str) -> str:
        """Full Repo entity rendered as markdown."""
        return _render_entity_markdown(storage.get_entity(EntityType.REPO, slug))

    @mcp.resource("context://task/{slug}")
    def task_resource(slug: str) -> str:
        """Full Task entity rendered as markdown."""
        return _render_entity_markdown(storage.get_entity(EntityType.TASK, slug))

    @mcp.resource("context://governance/{slug}")
    def governance_resource(slug: str) -> str:
        """Full Governance entity rendered as markdown."""
        return _render_entity_markdown(storage.get_entity(EntityType.GOVERNANCE, slug))

    # Single-subtopic views
    @mcp.resource("context://component/{slug}/{subtopic}")
    def component_subtopic(slug: str, subtopic: str) -> str:
        """One subtopic on a Component."""
        sub = storage.get_subtopic(EntityRef(type=EntityType.COMPONENT, slug=slug, subtopic=subtopic))
        if sub is None:
            raise KeyError(f"component:{slug}/{subtopic} not found")
        return sub.content

    @mcp.resource("context://repo/{slug}/{subtopic}")
    def repo_subtopic(slug: str, subtopic: str) -> str:
        """One subtopic on a Repo."""
        sub = storage.get_subtopic(EntityRef(type=EntityType.REPO, slug=slug, subtopic=subtopic))
        if sub is None:
            raise KeyError(f"repo:{slug}/{subtopic} not found")
        return sub.content

    @mcp.resource("context://task/{slug}/{subtopic}")
    def task_subtopic(slug: str, subtopic: str) -> str:
        """One subtopic on a Task."""
        sub = storage.get_subtopic(EntityRef(type=EntityType.TASK, slug=slug, subtopic=subtopic))
        if sub is None:
            raise KeyError(f"task:{slug}/{subtopic} not found")
        return sub.content

    @mcp.resource("context://governance/{slug}/{subtopic}")
    def governance_subtopic(slug: str, subtopic: str) -> str:
        """One subtopic on a Governance entity."""
        sub = storage.get_subtopic(EntityRef(type=EntityType.GOVERNANCE, slug=slug, subtopic=subtopic))
        if sub is None:
            raise KeyError(f"governance:{slug}/{subtopic} not found")
        return sub.content

    # Assembled task pack (distinct scheme to avoid colliding with {slug}/{subtopic})
    @mcp.resource("pack://task/{slug}")
    def task_pack_resource(slug: str) -> str:
        """Assembled markdown pack for a task: own notes + governance + all linked refs."""
        return _render_pack_markdown(storage.get_task_pack(slug))
