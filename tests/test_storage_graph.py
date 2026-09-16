from __future__ import annotations

from devspan.models import EntityRef, EntityType
from devspan.storage import Storage


def test_traverse_uses_and_suggest(storage: Storage) -> None:
    # Build a small uses graph: ui -> api -> db
    storage.create_entity(EntityType.COMPONENT, "db", description="Postgres")
    storage.create_entity(EntityType.COMPONENT, "api", description="REST API", uses=["db"])
    storage.create_entity(EntityType.COMPONENT, "ui", description="Frontend", uses=["api"])

    # Content must contain the exact phrase from task notes for the phrase FTS used by suggest
    storage.upsert_subtopic(
        EntityRef(type=EntityType.COMPONENT, slug="db", subtopic="overview"),
        "We use postgres. Add login and session handling flow uses sessions here.",
    )
    storage.upsert_subtopic(
        EntityRef(type=EntityType.COMPONENT, slug="api", subtopic="overview"),
        "API layer for Add login and session handling flow .",
    )

    # Create task without scaffold so its subtopics don't pollute the phrase query in suggest
    storage.create_entity(EntityType.TASK, "login", description="", scaffold=False)
    storage.upsert_subtopic(
        EntityRef(type=EntityType.TASK, slug="login", subtopic="notes"),
        "Add login and session handling flow",
    )
    # Link task initially to ui so anchors pick it up
    storage.link_task("login", ["component:ui"])

    # Suggestions should surface reachable components (api, db) via graph + FTS
    suggestions = storage.suggest_task_links("login", depth=3, top_k=5)
    refs = [s["ref"] for s in suggestions]
    # At minimum the api/db subtopics should be proposed
    assert any("component:api" in r or "component:db" in r for r in refs), f"suggestions were {refs}"

    # Direct traverse helper
    reachable = storage.traverse_uses(["ui"], depth=2)
    assert "api" in reachable and "db" in reachable
