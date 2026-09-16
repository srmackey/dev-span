from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class EntityType(str, Enum):
    COMPONENT = "component"
    REPO = "repo"
    TASK = "task"
    GOVERNANCE = "governance"


class ComponentKind(str, Enum):
    SYSTEM = "system"
    SERVICE = "service"
    API = "api"
    DATABASE = "database"
    LIBRARY = "library"
    TOOL = "tool"


class EntityRef(BaseModel):
    type: EntityType
    slug: str
    subtopic: str | None = None

    def __str__(self) -> str:
        if self.subtopic:
            return f"{self.type.value}:{self.slug}/{self.subtopic}"
        return f"{self.type.value}:{self.slug}"


class ExternalRef(BaseModel):
    system: str  # e.g. "jira", "github", "confluence"
    id: str      # e.g. "BUG-1234", "pr/456"
    url: str = ""


class EntityMeta(BaseModel):
    name: str
    description: str = ""
    created_at: str
    updated_at: str
    aliases: list[str] = Field(default_factory=list)
    # Component-only: subtype + outbound dep graph
    kind: ComponentKind | None = None
    uses: list[str] = Field(default_factory=list)
    # Repo-only: parent component slug
    component: str | None = None
    # Task-only: links + external refs
    links: list[str] = Field(default_factory=list)
    external_refs: list[ExternalRef] = Field(default_factory=list)
    # Any non-governance entity: references to governance entities
    governance: list[str] = Field(default_factory=list)


class Subtopic(BaseModel):
    slug: str
    content: str
    updated_at: str = ""
    # Optional source tracking for imported content.
    source_url: str = ""
    source_name: str = ""
    source_fetched_at: str = ""


class Entity(BaseModel):
    type: EntityType
    slug: str
    meta: EntityMeta
    subtopics: list[Subtopic] = Field(default_factory=list)


class TaskPack(BaseModel):
    task: Entity
    linked: list[tuple[str, str]] = Field(default_factory=list)
    governance: list[tuple[str, str]] = Field(default_factory=list)
    # Subtopic refs that were filtered out by focus-mode narrowing.
    # Pull them on demand via get_subtopic / get_context if the LLM needs more.
    dropped: list[str] = Field(default_factory=list)
